"""Cash advances and financial review: immutable commands, server-owned balances."""

import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from . import governance_models  # noqa: F401
from .audit import record
from .delivery_routes import Context, Database
from .expense_routes import expense, finish, rows, safe
from .expense_schemas import Exact
from .master_routes import find, require_current, write_lock
from .sync_routes import receipt
from .trip_models import Trip

router = APIRouter(prefix="/api/v1", tags=["Cash settlement and financial review"])
ZERO = Decimal("0.00")


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Exact | None = Field(None, gt=0, le=10000000, decimal_places=2)
    source_expense_id: uuid.UUID | None = None
    currency: Literal["PHP"] = "PHP"
    purpose: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def source(self):
        if (self.amount is None) == (self.source_expense_id is None):
            raise ValueError("Provide amount or recorded advance, not both.")
        return self


class Reason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=2000)

    @model_validator(mode="after")
    def meaningful(self):
        if len("".join(self.reason.split())) < 10:
            raise ValueError("Reason requires 10 non-whitespace characters.")
        return self


class Apply(Reason):
    expense_id: uuid.UUID


class Return(Reason):
    amount: Exact = Field(gt=0, le=10000000, decimal_places=2)
    currency: Literal["PHP"] = "PHP"


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_event_id: uuid.UUID | None
    records_confirmed: Literal[True]


class LegacyReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]


async def read_lock(db, ctx, cap):
    ctx.require(cap)
    await db.execute(
        text("SELECT id FROM organizations WHERE id=:org FOR SHARE"), dict(org=ctx.organization.id)
    )


async def raw_advance(db, ctx, identifier):
    found = await rows(
        db,
        "SELECT * FROM cash_advances WHERE organization_id=:org AND id=:id",
        org=ctx.organization.id,
        id=identifier,
    )
    if not found:
        raise HTTPException(404, "Cash advance not found.")
    return found[0]


async def advance_summary(db, ctx, a):
    history = await rows(
        db,
        """SELECT e.*,EXISTS(SELECT 1 FROM cash_advance_settlement_entries r WHERE r.reverses_id=e.id AND r.organization_id=e.organization_id) AS reversed FROM cash_advance_settlement_entries e WHERE e.organization_id=:org AND e.cash_advance_id=:id ORDER BY e.created_at,e.id""",
        org=ctx.organization.id,
        id=a["id"],
    )
    applied = sum(
        (
            e["amount"]
            for e in history
            if e["entry_type"] == "EXPENSE_APPLIED" and not e["reversed"]
        ),
        ZERO,
    )
    returned = sum(
        (e["amount"] for e in history if e["entry_type"] == "CASH_RETURNED" and not e["reversed"]),
        ZERO,
    )
    voided = any(e["entry_type"] == "VOID" for e in history)
    balance = ZERO if voided else a["amount_issued"] - applied - returned
    status = (
        "VOIDED"
        if voided
        else "SETTLED"
        if balance == 0
        else "PARTIALLY_SETTLED"
        if applied + returned
        else "ISSUED"
    )
    return {
        **a,
        "applied": applied,
        "returned": returned,
        "outstanding": balance,
        "status": status,
        "history": history,
    }


async def expense_value(db, ctx, trip, identifier):
    ctx.require("expenses.read")
    items = await rows(
        db,
        """SELECT e.id,e.driver_id,e.status,r.category,coalesce(p.amount,r.amount) amount,coalesce(p.voided,false) voided FROM trip_expenses e JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE e.organization_id=:org AND e.trip_id=:trip AND e.id=:id""",
        org=ctx.organization.id,
        trip=trip,
        id=identifier,
    )
    if not items:
        raise HTTPException(404, "Expense not found in this trip.")
    return items[0]


@router.get("/trips/{trip_id}/cash-advances")
async def advances(
    trip_id: uuid.UUID,
    ctx: Context,
    db: Database,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await read_lock(db, ctx, "cash_advance.read")
    await find(db, ctx, Trip, trip_id)
    items = await rows(
        db,
        "SELECT * FROM cash_advances WHERE organization_id=:org AND trip_id=:trip ORDER BY issued_at,id LIMIT :limit OFFSET :offset",
        org=ctx.organization.id,
        trip=trip_id,
        limit=limit,
        offset=offset,
    )
    total = await db.scalar(
        text("SELECT count(*) FROM cash_advances WHERE organization_id=:org AND trip_id=:trip"),
        dict(org=ctx.organization.id, trip=trip_id),
    )
    return safe(
        dict(
            items=[await advance_summary(db, ctx, a) for a in items],
            total=total,
            limit=limit,
            offset=offset,
        )
    )


@router.post("/trips/{trip_id}/cash-advances")
async def issue(
    trip_id: uuid.UUID,
    payload: Issue,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    await write_lock(db, ctx, "cash_advance.create")
    require_current(ctx, "cash_advance.read")
    trip = await find(db, ctx, Trip, trip_id)
    if trip.current_status == "CANCELLED":
        raise HTTPException(409, "Cancelled trip is read-only.")
    digest, replay = await receipt(
        db,
        ctx,
        idempotency_key,
        dict(command="cash_issue", trip=str(trip_id), payload=payload.model_dump(mode="json")),
    )
    if replay:
        return replay
    driver, amount = trip.driver_id, payload.amount
    if payload.source_expense_id:
        e = await expense_value(db, ctx, trip_id, payload.source_expense_id)
        if e["category"] != "DRIVER_CASH_ADVANCE" or e["status"] == "VOIDED" or e["voided"]:
            raise HTTPException(409, "Recorded advance is not eligible.")
        if await db.scalar(
            text("SELECT id FROM cash_advances WHERE source_expense_id=:id"), dict(id=e["id"])
        ):
            raise HTTPException(409, "Recorded advance was already reconciled.")
        driver, amount = e["driver_id"], e["amount"]
    if not driver:
        raise HTTPException(409, "Assign a driver before issuing an advance.")
    identifier = uuid.uuid4()
    await db.execute(
        text(
            """INSERT INTO cash_advances(id,organization_id,trip_id,driver_id,amount_issued,source_expense_id,purpose,issued_by) VALUES(:id,:org,:trip,:driver,:amount,:source,:purpose,:actor)"""
        ),
        dict(
            id=identifier,
            org=ctx.organization.id,
            trip=trip_id,
            driver=driver,
            amount=amount,
            source=payload.source_expense_id,
            purpose=payload.purpose,
            actor=ctx.user.id,
        ),
    )
    record(
        db,
        ctx,
        "cash_advance.created",
        "cash_advance",
        identifier,
        None,
        dict(
            trip_id=str(trip_id),
            amount=str(amount),
            source_expense_id=str(payload.source_expense_id) if payload.source_expense_id else None,
        ),
    )
    return await finish(
        db,
        ctx,
        trip,
        "cash_issue",
        idempotency_key,
        digest,
        {"advance": safe(await advance_summary(db, ctx, await raw_advance(db, ctx, identifier)))},
    )


async def settlement(db, ctx, identifier, payload, key, kind, reverse_id=None):
    await write_lock(db, ctx, "cash_advance.void" if kind == "VOID" else "cash_advance.settle")
    require_current(ctx, "cash_advance.read")
    a = await raw_advance(db, ctx, identifier)
    trip = await find(db, ctx, Trip, a["trip_id"])
    if trip.current_status == "CANCELLED":
        raise HTTPException(409, "Cancelled trip is read-only.")
    digest, replay = await receipt(
        db,
        ctx,
        key,
        dict(
            command="cash_" + kind,
            target=str(identifier),
            reverse=str(reverse_id),
            payload=payload.model_dump(mode="json"),
        ),
    )
    if replay:
        return replay
    s = await advance_summary(db, ctx, a)
    if s["status"] == "VOIDED":
        raise HTTPException(409, "Voided advance is read-only.")
    amount, expense = ZERO, None
    if kind == "VOID":
        if s["history"]:
            raise HTTPException(
                409, "Settlement history prevents voiding; preserve and reconcile the advance."
            )
    elif kind == "REVERSAL":
        original = next((e for e in s["history"] if e["id"] == reverse_id), None)
        if (
            not original
            or original["entry_type"] not in ("EXPENSE_APPLIED", "CASH_RETURNED")
            or original["reversed"]
        ):
            raise HTTPException(409, "Entry is not reversible.")
        amount = original["amount"]
    else:
        if kind == "EXPENSE_APPLIED":
            e = await expense_value(db, ctx, a["trip_id"], payload.expense_id)
            if (
                e["status"] != "REVIEWED"
                or e["voided"]
                or e["category"] == "DRIVER_CASH_ADVANCE"
                or e["driver_id"] != a["driver_id"]
            ):
                raise HTTPException(
                    409, "Apply a reviewed non-voided expense for the same trip and driver."
                )
            duplicate = await db.scalar(
                text(
                    """SELECT s.id FROM cash_advance_settlement_entries s WHERE s.organization_id=:org AND s.expense_id=:id AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries r WHERE r.reverses_id=s.id)"""
                ),
                dict(org=ctx.organization.id, id=e["id"]),
            )
            if duplicate:
                raise HTTPException(409, "Expense is already applied to an advance.")
            amount, expense = e["amount"], e["id"]
        else:
            amount = payload.amount
        if amount > s["outstanding"]:
            raise HTTPException(409, "Settlement exceeds outstanding balance.")
    eid = uuid.uuid4()
    await db.execute(
        text(
            """INSERT INTO cash_advance_settlement_entries(id,organization_id,trip_id,cash_advance_id,entry_type,amount,expense_id,reverses_id,reason,created_by) VALUES(:id,:org,:trip,:advance,:kind,:amount,:expense,:reverse,:reason,:actor)"""
        ),
        dict(
            id=eid,
            org=ctx.organization.id,
            trip=a["trip_id"],
            advance=identifier,
            kind=kind,
            amount=amount,
            expense=expense,
            reverse=reverse_id,
            reason=payload.reason,
            actor=ctx.user.id,
        ),
    )
    action = {
        "EXPENSE_APPLIED": "settlement_applied",
        "CASH_RETURNED": "cash_returned",
        "VOID": "voided",
        "REVERSAL": "reversal_created",
    }[kind]
    record(
        db,
        ctx,
        "cash_advance." + action,
        "cash_advance",
        identifier,
        None,
        dict(
            trip_id=str(a["trip_id"]), entry_id=str(eid), amount=str(amount), reason=payload.reason
        ),
    )
    summary = await advance_summary(db, ctx, a)
    if summary["status"] == "SETTLED" and s["status"] != "SETTLED":
        record(
            db,
            ctx,
            "cash_advance.settled",
            "cash_advance",
            identifier,
            None,
            dict(trip_id=str(a["trip_id"])),
        )
    return await finish(db, ctx, trip, "cash_" + kind, key, digest, {"advance": safe(summary)})


@router.post("/cash-advances/{identifier}/apply-expense")
async def apply_expense(
    identifier: uuid.UUID,
    payload: Apply,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await settlement(db, ctx, identifier, payload, idempotency_key, "EXPENSE_APPLIED")


@router.post("/cash-advances/{identifier}/cash-return")
async def cash_return(
    identifier: uuid.UUID,
    payload: Return,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await settlement(db, ctx, identifier, payload, idempotency_key, "CASH_RETURNED")


@router.post("/cash-advances/{identifier}/void")
async def void(
    identifier: uuid.UUID,
    payload: Reason,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await settlement(db, ctx, identifier, payload, idempotency_key, "VOID")


@router.post("/cash-advances/{identifier}/entries/{entry_id}/reverse")
async def reverse(
    identifier: uuid.UUID,
    entry_id: uuid.UUID,
    payload: Reason,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await settlement(db, ctx, identifier, payload, idempotency_key, "REVERSAL", entry_id)


async def legacy_expenses(db, ctx, trip_id):
    return await rows(
        db,
        """SELECT e.id,e.status,r.category,coalesce(p.amount,r.amount) AS amount,r.amount AS original_amount,
        r.occurred_at,r.description,r.reference_number,e.submitted_by,e.submitted_at,d.first_name,d.last_name
        FROM trip_expenses e JOIN expense_revisions r ON r.organization_id=e.organization_id AND r.expense_id=e.id AND r.revision_number=e.current_revision
        LEFT JOIN expense_effective_values p ON p.organization_id=e.organization_id AND p.expense_id=e.id
        LEFT JOIN legacy_expense_review_events l ON l.organization_id=e.organization_id AND l.expense_id=e.id AND l.action='ACCEPTED'
        JOIN drivers d ON d.organization_id=e.organization_id AND d.id=e.driver_id
        WHERE e.organization_id=:org AND e.trip_id=:trip AND e.status='SUBMITTED' AND r.category<>'DRIVER_CASH_ADVANCE'
        AND NOT coalesce(p.voided,false) AND l.id IS NULL ORDER BY e.submitted_at,e.id""",
        org=ctx.organization.id,
        trip=trip_id,
    )


async def review_state(db, ctx, trip_id):
    blockers = await db.scalar(text("SELECT financial_review_blockers(:trip)"), dict(trip=trip_id))
    latest = await rows(
        db,
        "SELECT * FROM trip_financial_review_events WHERE organization_id=:org AND trip_id=:trip ORDER BY sequence DESC LIMIT 1",
        org=ctx.organization.id,
        trip=trip_id,
    )
    last = latest[0] if latest else None
    status = (
        "NEEDS_ATTENTION"
        if blockers
        else last["status"]
        if last and last["status"] in ("APPROVED", "UNDER_REVIEW")
        else "READY_FOR_REVIEW"
    )
    return dict(
        status=status,
        blockers=blockers,
        latest_event_id=last["id"] if last else None,
        reviewed_by=last["created_by"] if status == "APPROVED" else None,
        reviewed_at=last["created_at"] if status == "APPROVED" else None,
    )


@router.get("/trips/{trip_id}/financial-review")
async def review_detail(
    trip_id: uuid.UUID,
    ctx: Context,
    db: Database,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await read_lock(db, ctx, "financial_review.read")
    for cap in (
        "cash_advance.read",
        "trip_financials.read",
        "trip_profitability.read",
        "expenses.read",
    ):
        ctx.require(cap)
    trip = await find(db, ctx, Trip, trip_id)
    from .profitability import calculate_many

    financial = (
        await calculate_many(db, ctx, [{"id": trip.id, "current_status": trip.current_status}])
    )[0]
    history = await rows(
        db,
        "SELECT * FROM trip_financial_review_events WHERE organization_id=:org AND trip_id=:trip ORDER BY sequence DESC LIMIT :limit OFFSET :offset",
        org=ctx.organization.id,
        trip=trip_id,
        limit=limit,
        offset=offset,
    )
    return safe(
        {
            **await review_state(db, ctx, trip_id),
            "financials": financial,
            "legacy_expenses": await legacy_expenses(db, ctx, trip_id),
            "history": history,
            "limit": limit,
            "offset": offset,
        }
    )


@router.get("/financial-review/legacy")
async def legacy_queue(
    ctx: Context,
    db: Database,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await read_lock(db, ctx, "financial_review.read")
    for cap in ("expenses.read", "trip_profitability.read"):
        ctx.require(cap)
    base = """ FROM trips t JOIN customers c ON c.organization_id=t.organization_id AND c.id=t.customer_id
      WHERE t.organization_id=:org AND t.current_status='COMPLETED' AND EXISTS(
        SELECT 1 FROM trip_expenses e JOIN expense_revisions r ON r.organization_id=e.organization_id AND r.expense_id=e.id AND r.revision_number=e.current_revision
        LEFT JOIN expense_effective_values p ON p.organization_id=e.organization_id AND p.expense_id=e.id
        LEFT JOIN legacy_expense_review_events l ON l.organization_id=e.organization_id AND l.expense_id=e.id AND l.action='ACCEPTED'
        WHERE e.organization_id=t.organization_id AND e.trip_id=t.id AND e.status='SUBMITTED' AND r.category<>'DRIVER_CASH_ADVANCE'
        AND NOT coalesce(p.voided,false) AND l.id IS NULL)"""
    total = await db.scalar(text("SELECT count(*)" + base), {"org": ctx.organization.id})
    items = await rows(
        db,
        """SELECT t.id,t.trip_number,t.current_status,t.completed_at,c.company_name,
        (SELECT count(*) FROM trip_expenses e JOIN expense_revisions r ON r.organization_id=e.organization_id AND r.expense_id=e.id AND r.revision_number=e.current_revision
         LEFT JOIN expense_effective_values p ON p.organization_id=e.organization_id AND p.expense_id=e.id
         LEFT JOIN legacy_expense_review_events l ON l.organization_id=e.organization_id AND l.expense_id=e.id AND l.action='ACCEPTED'
         WHERE e.organization_id=t.organization_id AND e.trip_id=t.id AND e.status='SUBMITTED' AND r.category<>'DRIVER_CASH_ADVANCE' AND NOT coalesce(p.voided,false) AND l.id IS NULL) AS unreviewed_expenses"""
        + base
        + " ORDER BY t.completed_at DESC,t.id LIMIT :limit OFFSET :offset",
        org=ctx.organization.id,
        limit=limit,
        offset=offset,
    )
    from .profitability import calculate_many
    financials = await calculate_many(db, ctx, items)
    mapped = {x["trip_id"]: x for x in financials}
    return safe({"items": [{**row, "financials": mapped.get(row["id"])} for row in items], "total": total, "limit": limit, "offset": offset})


@router.post("/expenses/{identifier}/legacy-review")
async def accept_legacy_expense(
    identifier: uuid.UUID,
    payload: LegacyReview,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    await write_lock(db, ctx, "financial_review.approve")
    for cap in ("financial_review.read", "expenses.read", "expenses.review"):
        require_current(ctx, cap)
    item = await expense(db, ctx, identifier)
    trip = await find(db, ctx, Trip, item["trip_id"])
    if trip.current_status != "COMPLETED":
        raise HTTPException(409, "Legacy review requires a completed trip.")
    details = await rows(
        db,
        """SELECT r.category,coalesce(p.voided,false) AS voided FROM expense_revisions r
        LEFT JOIN expense_effective_values p ON p.organization_id=r.organization_id AND p.expense_id=r.expense_id
        WHERE r.organization_id=:org AND r.expense_id=:id AND r.revision_number=:revision""",
        org=ctx.organization.id,
        id=identifier,
        revision=item["current_revision"],
    )
    if item["status"] != "SUBMITTED" or not details or details[0]["category"] == "DRIVER_CASH_ADVANCE" or details[0]["voided"]:
        raise HTTPException(409, "Legacy expense is not eligible for acceptance.")
    document = {"command": "legacy_expense_review", "expense": str(identifier), "payload": payload.model_dump(mode="json")}
    digest, replay = await receipt(db, ctx, idempotency_key, document)
    if replay:
        return replay
    event_id = uuid.uuid4()
    await db.execute(text("""INSERT INTO legacy_expense_review_events(id,organization_id,trip_id,expense_id,action,created_by)
        VALUES(:id,:org,:trip,:expense,'ACCEPTED',:actor)"""), dict(id=event_id, org=ctx.organization.id, trip=trip.id, expense=identifier, actor=ctx.user.id))
    record(db, ctx, "legacy_expense.reviewed", "expense", identifier, None, {"trip_id": str(trip.id), "expense_id": str(identifier), "action": "ACCEPTED"})
    result = {"event_id": str(event_id), "review": safe(await review_state(db, ctx, trip.id))}
    return await finish(db, ctx, trip, "legacy_review", idempotency_key, digest, result)


async def review_command(db, ctx, trip_id, payload, key, action):
    await write_lock(db, ctx, "financial_review.approve")
    for cap in (
        "financial_review.read",
        "cash_advance.read",
        "trip_financials.read",
        "expenses.read",
    ):
        require_current(ctx, cap)
    trip = await find(db, ctx, Trip, trip_id)
    digest, replay = await receipt(
        db,
        ctx,
        key,
        dict(
            command="financial_" + action,
            trip=str(trip_id),
            payload=payload.model_dump(mode="json"),
        ),
    )
    if replay:
        return replay
    state = await review_state(db, ctx, trip_id)
    if state["latest_event_id"] != payload.expected_event_id:
        raise HTTPException(409, "Financial records changed. Reload and review again.")
    if trip.current_status != "COMPLETED":
        raise HTTPException(409, "Complete the trip before financial review.")
    if action == "approve" and state["blockers"]:
        raise HTTPException(409, " ".join(state["blockers"]))
    if state["status"] == "APPROVED":
        raise HTTPException(409, "Financial review is already approved.")
    status = "APPROVED" if action == "approve" else "UNDER_REVIEW"
    await db.execute(
        text(
            """INSERT INTO trip_financial_review_events(id,organization_id,trip_id,status,reason,created_by) VALUES(:id,:org,:trip,:status,:reason,:actor)"""
        ),
        dict(
            id=uuid.uuid4(),
            org=ctx.organization.id,
            trip=trip_id,
            status=status,
            reason="Reviewer confirms all known financial records are synchronized and reviewed.",
            actor=ctx.user.id,
        ),
    )
    record(
        db,
        ctx,
        "financial_review." + ("approved" if action == "approve" else "started"),
        "trip",
        trip_id,
        None,
        dict(status=status, records_confirmed=True),
    )
    return await finish(
        db,
        ctx,
        trip,
        "financial_" + action,
        key,
        digest,
        {"review": safe(await review_state(db, ctx, trip_id))},
    )


@router.post("/trips/{trip_id}/financial-review/start")
async def start(
    trip_id: uuid.UUID,
    payload: Review,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await review_command(db, ctx, trip_id, payload, idempotency_key, "start")


@router.post("/trips/{trip_id}/financial-review/approve")
async def approve(
    trip_id: uuid.UUID,
    payload: Review,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await review_command(db, ctx, trip_id, payload, idempotency_key, "approve")
