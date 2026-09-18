"""Privileged append-only overlays. Completed trips and original costs never change."""

import json
import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator
from sqlalchemy import text

from . import adjustment_models  # noqa: F401
from .audit import record
from .delivery_routes import Context, Database
from .expense_routes import expense, finish, rows, safe
from .expense_schemas import decimal_string
from .master_routes import find, require_current, write_lock
from .sync_routes import receipt
from .trip_models import Trip

router = APIRouter(prefix="/api/v1", tags=["Closed-trip adjustments"])
FIELDS = {
    "AMOUNT_CORRECTION": "amount",
    "REFERENCE_CORRECTION": "reference_number",
    "DESCRIPTION_CORRECTION": "description",
    "ODOMETER_CORRECTION": "odometer",
    "VOID_ADJUSTMENT": "voided",
}


class ReasonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_sequence: int = Field(ge=0, strict=True)
    reason: str = Field(max_length=2000)

    @field_validator("reason")
    @classmethod
    def meaningful(cls, value):
        if len("".join(value.split())) < 10:
            raise ValueError(
                "Provide at least 10 non-whitespace characters explaining the correction."
            )
        return value.strip()


class AdjustmentInput(ReasonInput):
    target_id: uuid.UUID
    adjustment_type: Literal[
        "AMOUNT_CORRECTION",
        "REFERENCE_CORRECTION",
        "DESCRIPTION_CORRECTION",
        "ODOMETER_CORRECTION",
        "VOID_ADJUSTMENT",
    ]
    new_value: StrictStr | None = None

    @model_validator(mode="after")
    def value_check(self):
        kind = self.adjustment_type
        if kind in ("AMOUNT_CORRECTION", "ODOMETER_CORRECTION"):
            number = decimal_string(self.new_value)
            places = 2 if kind == "AMOUNT_CORRECTION" else 1
            if (
                number > 10000000
                or number < 0
                or (kind == "AMOUNT_CORRECTION" and number == 0)
                or number.as_tuple().exponent < -places
            ):
                raise ValueError("Invalid amount or odometer precision/range.")
            self.new_value = format(number, f".{places}f")
        elif kind == "VOID_ADJUSTMENT":
            if self.new_value is not None:
                raise ValueError("Void has no supplied value.")
        elif self.new_value is not None and len(self.new_value) > (
            120 if kind == "REFERENCE_CORRECTION" else 2000
        ):
            raise ValueError("Text exceeds limit.")
        return self


async def effective(db, ctx, identifier):
    result = await rows(
        db,
        """SELECT r.amount,r.odometer,r.description,r.reference_number,
       r.category,e.status='VOIDED' AS voided,0 AS sequence FROM trip_expenses e JOIN expense_revisions r
       ON r.organization_id=e.organization_id AND r.expense_id=e.id AND r.revision_number=e.current_revision
       WHERE e.organization_id=:org AND e.id=:id""",
        org=ctx.organization.id,
        id=identifier,
    )
    if not result:
        raise HTTPException(404, "Expense not found.")
    overlay = await rows(
        db,
        "SELECT amount,odometer,description,reference_number,voided,sequence FROM expense_effective_values WHERE organization_id=:org AND expense_id=:id",
        org=ctx.organization.id,
        id=identifier,
    )
    return safe({**result[0], **(overlay[0] if overlay else {})})


async def history(db, ctx, trip_id, limit=50, offset=0):
    return safe(
        await rows(
            db,
            """SELECT a.*,CASE WHEN a.reverses_id IS NOT NULL THEN 'REVERSAL'
      WHEN EXISTS(SELECT 1 FROM closed_trip_adjustments b WHERE b.organization_id=a.organization_id AND b.reverses_id=a.id) THEN 'REVERSED' ELSE 'APPLIED' END AS status
      FROM closed_trip_adjustments a WHERE a.organization_id=:org AND a.trip_id=:trip AND a.expense_id IS NOT NULL ORDER BY a.created_at,a.id LIMIT :limit OFFSET :offset""",
            org=ctx.organization.id,
            trip=trip_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/trips/{trip_id}/adjustments")
async def list_adjustments(
    trip_id: uuid.UUID,
    ctx: Context,
    db: Database,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    ctx.require("closed_trip_adjustments.read")
    await find(db, ctx, Trip, trip_id)
    count = await db.scalar(
        text(
            "SELECT count(*) FROM closed_trip_adjustments WHERE organization_id=:org AND trip_id=:trip AND expense_id IS NOT NULL"
        ),
        {"org": ctx.organization.id, "trip": trip_id},
    )
    return {
        "items": await history(db, ctx, trip_id, limit, offset),
        "total": count,
        "limit": limit,
        "offset": offset,
    }


async def apply(db, ctx, trip_id, data, key, reverse_id=None):
    action = "reverse" if reverse_id else "create"
    await write_lock(db, ctx, "closed_trip_adjustments." + action)
    require_current(ctx, "closed_trip_adjustments.read")
    require_current(ctx, "expenses.read")
    trip = await find(db, ctx, Trip, trip_id)
    if trip.current_status != "COMPLETED":
        raise HTTPException(409, "Administrative adjustments require a completed trip.")
    doc = {
        "command": "adjustment_" + action,
        "trip": str(trip_id),
        "reverse": str(reverse_id) if reverse_id else None,
        "payload": data.model_dump(mode="json"),
    }
    digest, replay = await receipt(db, ctx, key, doc)
    if replay:
        return replay
    previous = None
    if reverse_id:
        values = await rows(
            db,
            """SELECT a.* FROM closed_trip_adjustments a WHERE a.organization_id=:org AND a.trip_id=:trip
         AND a.reverses_id IS NULL AND NOT EXISTS(SELECT 1 FROM closed_trip_adjustments b WHERE b.organization_id=a.organization_id AND b.reverses_id=a.id)
         AND a.expense_id=(SELECT expense_id FROM closed_trip_adjustments WHERE organization_id=:org AND id=:id)
         ORDER BY a.sequence DESC LIMIT 1""",
            org=ctx.organization.id,
            trip=trip_id,
            id=reverse_id,
        )
        if not values or values[0]["id"] != reverse_id:
            raise HTTPException(
                409, "Reverse the latest active adjustment first; entries cannot be reversed twice."
            )
        previous = values[0]
    target = previous["expense_id"] if previous else data.target_id
    original = await expense(db, ctx, target)
    if original["trip_id"] != trip_id:
        raise HTTPException(404, "Expense not found.")
    current = await effective(db, ctx, target)
    if current["sequence"] != data.expected_sequence:
        raise HTTPException(409, "Adjustment history changed. Reload before trying again.")
    if original["status"] == "VOIDED" or (current["voided"] and not previous):
        raise HTTPException(
            409, "Reverse the administrative void before adjusting; original voids are immutable."
        )
    kind = "REVERSAL" if previous else data.adjustment_type
    field = previous["field_name"] if previous else FIELDS[kind]
    value = (
        previous["old_value"]
        if previous
        else (True if kind == "VOID_ADJUSTMENT" else data.new_value)
    )
    if field == "odometer" and current["category"] != "FUEL":
        raise HTTPException(422, "Odometer correction requires Fuel.")
    if field == "description" and current["category"] == "OTHER" and len((value or "").strip()) < 3:
        raise HTTPException(422, "Other requires an explanation.")
    if value == current[field]:
        raise HTTPException(409, "The effective value is unchanged.")
    delta = Decimal(value) - Decimal(current[field]) if field == "amount" else None
    identifier = uuid.uuid4()
    await db.execute(
        text("""INSERT INTO closed_trip_adjustments(id,organization_id,trip_id,expense_id,source_revision,sequence,adjustment_type,field_name,old_value,new_value,amount_delta,reason,created_by,reverses_id)
    VALUES(:id,:org,:trip,:expense,:revision,:sequence,:kind,:field,CAST(:old AS jsonb),CAST(:new AS jsonb),:delta,:reason,:actor,:reverse)"""),
        {
            "id": identifier,
            "org": ctx.organization.id,
            "trip": trip_id,
            "expense": target,
            "revision": original["current_revision"],
            "sequence": current["sequence"] + 1,
            "kind": kind,
            "field": field,
            "old": json.dumps(current[field]),
            "new": json.dumps(value),
            "delta": delta,
            "reason": data.reason,
            "actor": ctx.user.id,
            "reverse": reverse_id,
        },
    )
    metadata = safe(
        {
            "trip_id": trip_id,
            "expense_id": target,
            "field": field,
            "old": current[field],
            "new": value,
            "delta": delta,
            "reason": data.reason,
            "reverses_id": reverse_id,
        }
    )
    for verb in ("reversed",) if previous else ("created", "applied"):
        record(
            db,
            ctx,
            "closed_trip_adjustment." + verb,
            "closed_trip_adjustment",
            identifier,
            None,
            metadata,
        )
    return await finish(
        db,
        ctx,
        trip,
        "adjustment_" + action,
        key,
        digest,
        {"adjustment_id": str(identifier), "effective": await effective(db, ctx, target)},
    )


@router.post("/trips/{trip_id}/adjustments")
async def create_adjustment(
    trip_id: uuid.UUID,
    payload: AdjustmentInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await apply(db, ctx, trip_id, payload, idempotency_key)


@router.post("/adjustments/{identifier}/reverse")
async def reverse_adjustment(
    identifier: uuid.UUID,
    payload: ReasonInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    ctx.require("closed_trip_adjustments.reverse")
    ctx.require("closed_trip_adjustments.read")
    found = await rows(
        db,
        "SELECT trip_id,revenue_id FROM closed_trip_adjustments WHERE organization_id=:org AND id=:id",
        org=ctx.organization.id,
        id=identifier,
    )
    if not found:
        raise HTTPException(404, "Adjustment not found.")
    if found[0]["revenue_id"]:
        from .financial_routes import adjust_revenue

        return await adjust_revenue(
            db, ctx, found[0]["revenue_id"], payload, idempotency_key, identifier
        )
    return await apply(db, ctx, found[0]["trip_id"], payload, idempotency_key, identifier)
