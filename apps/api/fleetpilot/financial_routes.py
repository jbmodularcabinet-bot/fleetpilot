"""Revenue commands reuse organization locking, replay receipts and adjustment events."""

import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from . import financial_models  # noqa: F401
from .adjustment_routes import FIELDS, AdjustmentInput, ReasonInput
from .audit import record
from .delivery_routes import Context, Database
from .expense_routes import finish, rows, safe
from .expense_schemas import Exact
from .master_routes import find, require_current, write_lock
from .permissions import resolve_permissions
from .profitability import calculate_many
from .sync_routes import receipt
from .trip_models import Trip

router = APIRouter(prefix="/api/v1", tags=["Trip financial performance"])


class RevenueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revenue_type: Literal[
        "BASE_TRIP_CHARGE", "SURCHARGE", "WAITING_TIME", "SPECIAL_HANDLING", "OTHER"
    ]
    amount: Exact = Field(gt=0, le=10000000, decimal_places=2)
    currency: Literal["PHP"] = "PHP"
    description: str | None = Field(None, max_length=2000)
    reference_number: str | None = Field(None, max_length=120)

    @model_validator(mode="after")
    def other(self):
        if self.revenue_type == "OTHER" and len((self.description or "").strip()) < 3:
            raise ValueError("Other requires an explanation.")
        return self


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_sequence: int = Field(ge=0, strict=True)


async def revenue(db, ctx, identifier):
    ctx.require("trip_financials.read")
    found = await rows(
        db,
        """SELECT r.*, coalesce(p.amount,r.amount) AS effective_amount,coalesce(p.sequence,0) AS sequence,
      coalesce(p.voided,false) AS administratively_voided,
      CASE WHEN p.revenue_id IS NULL THEN r.description ELSE p.description END AS effective_description,
      CASE WHEN p.revenue_id IS NULL THEN r.reference_number ELSE p.reference_number END AS effective_reference_number
      FROM trip_revenue r LEFT JOIN revenue_effective_values p ON p.organization_id=r.organization_id AND p.revenue_id=r.id
      WHERE r.organization_id=:org AND r.id=:id""",
        org=ctx.organization.id,
        id=identifier,
    )
    if not found:
        raise HTTPException(404, "Revenue not found.")
    return found[0]


async def financial_access(db, ctx):
    for cap in (
        "trip_financials.read",
        "trip_profitability.read",
        "expenses.read",
        "cash_advance.read",
        "financial_review.read",
    ):
        ctx.require(cap)
    # All financial writers use the organization lock; keep a coherent read snapshot.
    await db.execute(
        text("SELECT id FROM organizations WHERE id=:org FOR SHARE"), {"org": ctx.organization.id}
    )


@router.get("/trips/{trip_id}/profitability")
@router.get("/trips/{trip_id}/financials")
async def financials(trip_id: uuid.UUID, ctx: Context, db: Database):
    await financial_access(db, ctx)
    trip = await find(db, ctx, Trip, trip_id)
    return (
        await calculate_many(db, ctx, [{"id": trip.id, "current_status": trip.current_status}])
    )[0]


@router.get("/trips/{trip_id}/revenue")
async def list_revenue(
    trip_id: uuid.UUID,
    ctx: Context,
    db: Database,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    ctx.require("trip_financials.read")
    await find(db, ctx, Trip, trip_id)
    items = await rows(
        db,
        """SELECT r.*,coalesce(p.amount,r.amount) AS effective_amount,coalesce(p.sequence,0) AS sequence,
      coalesce(p.voided,false) AS administratively_voided,CASE WHEN p.revenue_id IS NULL THEN r.description ELSE p.description END AS effective_description,
      CASE WHEN p.revenue_id IS NULL THEN r.reference_number ELSE p.reference_number END AS effective_reference_number
      FROM trip_revenue r LEFT JOIN revenue_effective_values p ON p.revenue_id=r.id AND p.organization_id=r.organization_id
      WHERE r.organization_id=:org AND r.trip_id=:trip ORDER BY r.created_at,r.id LIMIT :limit OFFSET :offset""",
        org=ctx.organization.id,
        trip=trip_id,
        limit=limit,
        offset=offset,
    )
    count = await db.scalar(
        text("SELECT count(*) FROM trip_revenue WHERE organization_id=:org AND trip_id=:trip"),
        {"org": ctx.organization.id, "trip": trip_id},
    )
    return safe({"items": items, "total": count, "limit": limit, "offset": offset})


@router.get("/trip-revenue/{identifier}")
async def detail(identifier: uuid.UUID, ctx: Context, db: Database):
    item = await revenue(db, ctx, identifier)
    history = []
    if "closed_trip_adjustments.read" in resolve_permissions(
        ctx.membership.role, ctx.membership.permissions_json
    ):
        history = await rows(
            db,
            """SELECT a.*,CASE WHEN a.reverses_id IS NOT NULL THEN 'REVERSAL' WHEN EXISTS(SELECT 1 FROM closed_trip_adjustments b WHERE b.reverses_id=a.id AND b.organization_id=a.organization_id) THEN 'REVERSED' ELSE 'APPLIED' END AS adjustment_status
          FROM closed_trip_adjustments a WHERE organization_id=:org AND revenue_id=:id ORDER BY sequence""",
            org=ctx.organization.id,
            id=identifier,
        )
    return safe({**item, "history": history})


@router.post("/trips/{trip_id}/revenue")
async def create(
    trip_id: uuid.UUID,
    payload: RevenueInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    await write_lock(db, ctx, "trip_revenue.create")
    require_current(ctx, "trip_financials.read")
    trip = await find(db, ctx, Trip, trip_id)
    if trip.current_status == "CANCELLED":
        raise HTTPException(409, "Cancelled trips cannot receive revenue.")
    digest, replay = await receipt(
        db,
        ctx,
        idempotency_key,
        {
            "command": "revenue_create",
            "trip": str(trip_id),
            "payload": payload.model_dump(mode="json"),
        },
    )
    if replay:
        return replay
    identifier = uuid.uuid4()
    await db.execute(
        text("""INSERT INTO trip_revenue(id,organization_id,trip_id,revenue_type,amount,currency,description,reference_number,created_by)
      VALUES(:id,:org,:trip,:revenue_type,:amount,:currency,:description,:reference_number,:actor)"""),
        dict(
            id=identifier,
            org=ctx.organization.id,
            trip=trip_id,
            actor=ctx.user.id,
            **payload.model_dump(),
        ),
    )
    record(
        db,
        ctx,
        "trip_revenue.created",
        "trip_revenue",
        identifier,
        None,
        {
            "trip_id": str(trip_id),
            "amount": str(payload.amount),
            "revenue_type": payload.revenue_type,
        },
    )
    return await finish(
        db,
        ctx,
        trip,
        "revenue_create",
        idempotency_key,
        digest,
        {"revenue": safe(await revenue(db, ctx, identifier))},
    )


async def mutate(identifier, payload, ctx, db, key, action):
    await write_lock(db, ctx, "trip_revenue." + action)
    require_current(ctx, "trip_financials.read")
    item = await revenue(db, ctx, identifier)
    trip = await find(db, ctx, Trip, item["trip_id"])
    if trip.current_status == "CANCELLED":
        raise HTTPException(409, "Cancelled trip is read-only.")
    digest, replay = await receipt(
        db,
        ctx,
        key,
        {
            "command": "revenue_" + action,
            "target": str(identifier),
            "payload": payload.model_dump(mode="json"),
        },
    )
    if replay:
        return replay
    if (
        item["sequence"] != payload.expected_sequence
        or item["status"] == "VOIDED"
        or item["administratively_voided"]
    ):
        raise HTTPException(409, "Revenue changed or is voided. Reload.")
    if action == "review":
        if item["status"] != "SUBMITTED":
            raise HTTPException(409, "Already reviewed.")
        fields = "status='REVIEWED',reviewed_by=:actor,reviewed_at=clock_timestamp()"
    else:
        if trip.current_status == "COMPLETED":
            raise HTTPException(
                409, "Use an explicit administrative void adjustment for a completed trip."
            )
        fields = "status='VOIDED',voided_by=:actor,voided_at=clock_timestamp(),void_reason=:reason"
    await db.execute(
        text("UPDATE trip_revenue SET " + fields + " WHERE organization_id=:org AND id=:id"),
        dict(
            org=ctx.organization.id,
            id=identifier,
            actor=ctx.user.id,
            reason=getattr(payload, "reason", None),
        ),
    )
    record(
        db,
        ctx,
        "trip_revenue." + ("reviewed" if action == "review" else "voided"),
        "trip_revenue",
        identifier,
        None,
        {"trip_id": str(trip.id), "reason": getattr(payload, "reason", None)},
    )
    return await finish(
        db,
        ctx,
        trip,
        "revenue_" + action,
        key,
        digest,
        {"revenue": safe(await revenue(db, ctx, identifier))},
    )


@router.post("/trip-revenue/{identifier}/review")
async def review(
    identifier: uuid.UUID,
    payload: ReviewInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await mutate(identifier, payload, ctx, db, idempotency_key, "review")


@router.post("/trip-revenue/{identifier}/void")
async def void(
    identifier: uuid.UUID,
    payload: ReasonInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await mutate(identifier, payload, ctx, db, idempotency_key, "void")


async def adjust_revenue(db, ctx, identifier, payload, key, reverse_id=None):
    await write_lock(
        db,
        ctx,
        "closed_trip_adjustments.reverse" if reverse_id else "closed_trip_adjustments.create",
    )
    require_current(ctx, "closed_trip_adjustments.read")
    require_current(ctx, "trip_financials.read")
    item = await revenue(db, ctx, identifier)
    trip = await find(db, ctx, Trip, item["trip_id"])
    if trip.current_status == "CANCELLED":
        raise HTTPException(409, "Cancelled trip is read-only.")
    digest, replay = await receipt(
        db,
        ctx,
        key,
        {
            "command": "revenue_adjust",
            "target": str(identifier),
            "reverse": str(reverse_id) if reverse_id else None,
            "payload": payload.model_dump(mode="json"),
        },
    )
    if replay:
        return replay
    if payload.expected_sequence != item["sequence"] or item["status"] == "VOIDED":
        raise HTTPException(409, "Revenue changed or originally voided.")
    previous = None
    if reverse_id:
        active = await rows(
            db,
            """SELECT a.* FROM closed_trip_adjustments a WHERE a.organization_id=:org AND a.revenue_id=:id AND a.reverses_id IS NULL AND NOT EXISTS(SELECT 1 FROM closed_trip_adjustments b WHERE b.organization_id=a.organization_id AND b.reverses_id=a.id) ORDER BY a.sequence DESC LIMIT 1""",
            org=ctx.organization.id,
            id=identifier,
        )
        if not active or active[0]["id"] != reverse_id:
            raise HTTPException(409, "Reverse latest active adjustment first.")
        previous = active[0]
    else:
        if payload.target_id != identifier:
            raise HTTPException(404, "Revenue target not found.")
        if payload.adjustment_type == "ODOMETER_CORRECTION":
            raise HTTPException(422, "Revenue has no odometer.")
        if item["administratively_voided"]:
            raise HTTPException(409, "Reverse void first.")
    field = previous["field_name"] if previous else FIELDS[payload.adjustment_type]
    value = (
        previous["old_value"] if previous else (True if field == "voided" else payload.new_value)
    )
    original = {
        "amount": format(item["effective_amount"], ".2f"),
        "description": item["effective_description"],
        "reference_number": item["effective_reference_number"],
        "voided": item["administratively_voided"],
    }[field]
    if value == original:
        raise HTTPException(409, "Effective value unchanged.")
    if (
        field == "description"
        and item["revenue_type"] == "OTHER"
        and len((value or "").strip()) < 3
    ):
        raise HTTPException(422, "Other requires notes.")
    delta = Decimal(value) - Decimal(original) if field == "amount" else None
    aid = uuid.uuid4()
    await db.execute(
        text("""INSERT INTO closed_trip_adjustments(id,organization_id,trip_id,revenue_id,sequence,adjustment_type,field_name,old_value,new_value,amount_delta,reason,created_by,reverses_id)
      VALUES(:id,:org,:trip,:revenue,:seq,:kind,:field,CAST(:old AS jsonb),CAST(:new AS jsonb),:delta,:reason,:actor,:reverse)"""),
        dict(
            id=aid,
            org=ctx.organization.id,
            trip=trip.id,
            revenue=identifier,
            seq=item["sequence"] + 1,
            kind="REVERSAL" if previous else payload.adjustment_type,
            field=field,
            old=json.dumps(original),
            new=json.dumps(value),
            delta=delta,
            reason=payload.reason,
            actor=ctx.user.id,
            reverse=reverse_id,
        ),
    )
    metadata = safe(
        {
            "trip_id": trip.id,
            "revenue_id": identifier,
            "adjustment_id": aid,
            "field": field,
            "old": original,
            "new": value,
            "delta": delta,
            "reason": payload.reason,
        }
    )
    for verb in ["reversed"] if previous else ["created", "applied"]:
        record(
            db, ctx, "closed_trip_adjustment." + verb, "closed_trip_adjustment", aid, None, metadata
        )
    record(db, ctx, "trip_revenue.corrected", "trip_revenue", identifier, None, metadata)
    if field == "voided" and value is True:
        record(db, ctx, "trip_revenue.voided", "trip_revenue", identifier, None, metadata)
    return await finish(
        db,
        ctx,
        trip,
        "revenue_adjust",
        key,
        digest,
        {"adjustment_id": str(aid), "revenue": safe(await revenue(db, ctx, identifier))},
    )


@router.post("/trip-revenue/{identifier}/correct")
async def correct(
    identifier: uuid.UUID,
    payload: AdjustmentInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await adjust_revenue(db, ctx, identifier, payload, idempotency_key)


@router.get("/profitability/trips")
async def profitability_list(
    ctx: Context,
    db: Database,
    customer_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    status: Literal[
        "SCHEDULED",
        "DISPATCHED",
        "PICKUP",
        "LOADED",
        "IN_TRANSIT",
        "DELIVERED",
        "COMPLETED",
        "CANCELLED",
    ]
    | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    search: str = Query("", max_length=160),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: Literal["scheduled_pickup_at", "trip_number"] = "scheduled_pickup_at",
    direction: Literal["asc", "desc"] = "desc",
):
    await financial_access(db, ctx)
    if any(v is not None and v.tzinfo is None for v in (date_from, date_to)):
        raise HTTPException(422, "Dates require timezone.")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Invalid date range.")
    filters = ["t.organization_id=:org"]
    params = {"org": ctx.organization.id, "limit": limit, "offset": offset}
    for field, value in (
        ("customer_id", customer_id),
        ("vehicle_id", vehicle_id),
        ("driver_id", driver_id),
        ("current_status", status),
    ):
        if value is not None:
            filters.append("t." + field + "=:" + field)
            params[field] = value
    for label, op, value in (("date_from", ">=", date_from), ("date_to", "<=", date_to)):
        if value:
            filters.append("t.scheduled_pickup_at" + op + ":" + label)
            params[label] = value
    if search:
        filters.append("(t.trip_number ILIKE :search OR c.company_name ILIKE :search)")
        params["search"] = "%" + search + "%"
    join = (
        " FROM trips t JOIN customers c ON c.organization_id=t.organization_id AND c.id=t.customer_id WHERE "
        + " AND ".join(filters)
    )
    count = await db.scalar(text("SELECT count(*)" + join), params)
    trips = await rows(
        db,
        "SELECT t.id,t.trip_number,t.current_status,t.scheduled_pickup_at,c.company_name AS customer_name"
        + join
        + " ORDER BY t."
        + sort
        + " "
        + direction
        + ",t.id LIMIT :limit OFFSET :offset",
        **params,
    )
    calculated = await calculate_many(db, ctx, trips)
    return safe(
        {
            "items": [{**t, **p} for t, p in zip(trips, calculated, strict=True)],
            "total": count,
            "limit": limit,
            "offset": offset,
        }
    )
