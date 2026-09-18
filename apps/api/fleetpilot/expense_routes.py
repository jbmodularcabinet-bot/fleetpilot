"""Versioned operational costs. Explicit SQL keeps financial aggregates in PostgreSQL."""

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from . import expense_models  # noqa: F401 -- register domain metadata
from .audit import record
from .delivery_routes import Context, Database
from .evidence_storage import MAX_FILE_BYTES, storage, validate_image
from .expense_schemas import CorrectionInput, ExpenseInput, ReviewInput, VoidInput
from .master_models import Vehicle
from .master_routes import find, require_current, write_lock
from .trip_models import Trip
from .trip_routes import own_trip, touch, version_check

router = APIRouter(prefix="/api/v1", tags=["Trip expenses"])


def safe(value):
    return jsonable_encoder(value, custom_encoder={Decimal: lambda x: format(x, "f")})


def capability(ctx, action):
    if ctx.membership.role == "DRIVER":
        return "driver_expense.read_own" if action == "read" else "driver_expense.create_own"
    return "expenses." + action


async def trip_access(db, ctx, identifier, action="read"):
    if ctx.membership.role == "DRIVER" and action not in ("read", "create"):
        raise HTTPException(403, "Owner review permission required.")
    ctx.require(capability(ctx, action))
    return (
        await own_trip(db, ctx, identifier)
        if ctx.membership.role == "DRIVER"
        else await find(db, ctx, Trip, identifier)
    )


async def rows(db, sql, **params):
    return [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]


async def expense(db, ctx, identifier):
    result = await rows(
        db,
        "SELECT * FROM trip_expenses WHERE organization_id=:org AND id=:id",
        org=ctx.organization.id,
        id=identifier,
    )
    if not result:
        raise HTTPException(404, "Expense not found.")
    await trip_access(db, ctx, result[0]["trip_id"])
    return result[0]


async def detail(db, ctx, identifier):
    item = await expense(db, ctx, identifier)
    revisions = await rows(
        db,
        "SELECT * FROM expense_revisions WHERE organization_id=:org AND expense_id=:id ORDER BY revision_number",
        org=ctx.organization.id,
        id=identifier,
    )
    evidence = await rows(
        db,
        "SELECT id,expense_id,original_filename,content_type,file_size,checksum,uploaded_by,uploaded_at,status,supersedes_id FROM expense_evidence WHERE organization_id=:org AND expense_id=:id ORDER BY uploaded_at,id",
        org=ctx.organization.id,
        id=identifier,
    )
    from .adjustment_routes import effective

    return safe(
        {
            **item,
            "effective": await effective(db, ctx, identifier),
            "current": next(
                r for r in revisions if r["revision_number"] == item["current_revision"]
            ),
            "revisions": revisions,
            "evidence": evidence,
        }
    )


def audit(db, ctx, verb, trip, identifier, category, amount=None, before=None, after=None):
    metadata = {
        "trip_id": str(trip.id),
        "expense_id": str(identifier),
        "category": category,
        "amount": str(amount) if amount is not None else None,
    }
    record(db, ctx, "expense." + verb, "expense", identifier, before, {**metadata, **(after or {})})
    if category == "FUEL":
        record(
            db, ctx, "fuel." + verb, "expense", identifier, before, {**metadata, **(after or {})}
        )


async def writable(db, ctx, trip, version):
    version_check(trip, version)
    if trip.current_status == "SCHEDULED" or not trip.vehicle_id or not trip.driver_id:
        raise HTTPException(409, "Dispatch an assigned trip before recording costs.")


async def odometer_check(db, ctx, trip, data, vehicle_id=None):
    if data.category != "FUEL":
        return
    if ctx.membership.role != "DRIVER":
        require_current(ctx, "fuel.create")
    vehicle_id = uuid.UUID(str(vehicle_id or trip.vehicle_id))
    vehicle = await find(db, ctx, Vehicle, vehicle_id)
    trusted = await db.scalar(
        text(
            "SELECT reviewed_fuel_odometer FROM vehicles WHERE organization_id=:org AND id=:vehicle"
        ),
        {"org": ctx.organization.id, "vehicle": vehicle_id},
    )
    minimum = max(vehicle.odometer or Decimal(0), trusted or Decimal(0))
    if data.odometer is not None and data.odometer < minimum:
        raise HTTPException(409, f"Odometer must be at least the trusted reading of {minimum} km.")


async def revision(db, ctx, trip, identifier, number, data, reason=None, vehicle_id=None):
    await odometer_check(db, ctx, trip, data, vehicle_id)
    values = data.model_dump(exclude={"expected_version", "reason"})
    values.update(
        id=uuid.uuid4(),
        org=ctx.organization.id,
        trip=trip.id,
        expense=identifier,
        number=number,
        actor=ctx.user.id,
        reason=reason,
        amount=data.total,
    )
    await db.execute(
        text("""INSERT INTO expense_revisions(id,organization_id,trip_id,expense_id,revision_number,
      category,currency,amount,occurred_at,description,vendor_name,reference_number,liters,price_per_liter,odometer,created_by,reason)
      VALUES(:id,:org,:trip,:expense,:number,:category,:currency,:amount,:occurred_at,:description,:vendor_name,:reference_number,:liters,:price_per_liter,:odometer,:actor,:reason)"""),
        values,
    )


async def create(db, ctx, trip, data):
    await writable(db, ctx, trip, data.expected_version)
    identifier = uuid.uuid4()
    await db.execute(
        text("""INSERT INTO trip_expenses(id,organization_id,trip_id,vehicle_id,driver_id,submission_source,submitted_by)
      VALUES(:id,:org,:trip,:vehicle,:driver,:source,:actor)"""),
        dict(
            id=identifier,
            org=ctx.organization.id,
            trip=trip.id,
            vehicle=trip.vehicle_id,
            driver=trip.driver_id,
            source="DRIVER_APP" if ctx.membership.role == "DRIVER" else "OWNER_WEB",
            actor=ctx.user.id,
        ),
    )
    await revision(db, ctx, trip, identifier, 1, data)
    audit(db, ctx, "created", trip, identifier, data.category, data.total)
    await touch(db, ctx, trip)
    await db.flush()
    return {"expense": await detail(db, ctx, identifier), "trip_version": trip.version}


async def command(db, ctx, trip_id, action, key, document):
    from .sync_routes import receipt

    await write_lock(db, ctx, capability(ctx, action))
    trip = await trip_access(db, ctx, trip_id, action)
    await db.refresh(trip)
    if document.get("payload", {}).get("category") == "FUEL" and ctx.membership.role != "DRIVER":
        require_current(ctx, "fuel.create")
    if action == "review":
        category = await db.scalar(
            text("""SELECT r.category FROM trip_expenses e JOIN expense_revisions r
            ON r.organization_id=e.organization_id AND r.expense_id=e.id AND r.revision_number=e.current_revision
            WHERE e.organization_id=:org AND e.id=:id"""),
            {"org": ctx.organization.id, "id": uuid.UUID(document["expense"])},
        )
        if category == "FUEL":
            require_current(ctx, "fuel.review")
    digest, replay = await receipt(db, ctx, key, document)
    return trip, digest, replay


async def finish(db, ctx, trip, action, key, digest, result):
    from .sync_routes import finish as sync_finish

    return await sync_finish(db, ctx, trip, action, key, digest, datetime.now(timezone.utc), result)


@router.post("/trips/{trip_id}/expenses")
async def submit(
    trip_id: uuid.UUID,
    payload: ExpenseInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    document = {
        "command": "expense",
        "trip": str(trip_id),
        "payload": payload.model_dump(mode="json"),
    }
    trip, digest, replay = await command(db, ctx, trip_id, "create", idempotency_key, document)
    if replay:
        return replay
    return await finish(
        db, ctx, trip, "expense", idempotency_key, digest, await create(db, ctx, trip, payload)
    )


@router.get("/expenses/{identifier}")
async def get_expense(identifier: uuid.UUID, ctx: Context, db: Database):
    return await detail(db, ctx, identifier)


async def listing(db, ctx, where, params, limit, offset):
    join = """ FROM trip_expenses e JOIN expense_revisions r ON r.organization_id=e.organization_id
      AND r.expense_id=e.id AND r.revision_number=e.current_revision JOIN trips t ON t.id=e.trip_id AND t.organization_id=e.organization_id
      JOIN vehicles v ON v.id=e.vehicle_id AND v.organization_id=e.organization_id
      JOIN drivers d ON d.id=e.driver_id AND d.organization_id=e.organization_id """
    join += " LEFT JOIN expense_effective_values av ON av.organization_id=e.organization_id AND av.expense_id=e.id "
    params = {"org": ctx.organization.id, **params}
    where = " WHERE e.organization_id=:org AND " + where
    count = await db.scalar(text("SELECT count(*)" + join + where), params)
    items = await rows(
        db,
        "SELECT e.*, r.category,coalesce(av.amount,r.amount) AS amount,r.amount AS original_amount,r.currency,r.occurred_at,r.liters,r.price_per_liter,CASE WHEN av.expense_id IS NULL THEN r.odometer ELSE av.odometer END AS odometer,CASE WHEN av.expense_id IS NULL THEN r.description ELSE av.description END AS description,r.vendor_name,CASE WHEN av.expense_id IS NULL THEN r.reference_number ELSE av.reference_number END AS reference_number,coalesce(av.voided,false) AS administratively_voided,coalesce(av.sequence,0) AS adjustment_sequence,t.trip_number,v.unit_number,d.first_name,d.last_name"
        + join
        + where
        + " ORDER BY e.submitted_at DESC,e.id LIMIT :limit OFFSET :offset",
        **params,
        limit=limit,
        offset=offset,
    )
    totals = await rows(
        db,
        """SELECT r.category, coalesce(sum(coalesce(av.amount,r.amount)) FILTER(WHERE e.status<>'VOIDED' AND NOT coalesce(av.voided,false)),0) AS submitted_total,
      coalesce(sum(coalesce(av.amount,r.amount)) FILTER(WHERE e.status='REVIEWED' AND NOT coalesce(av.voided,false)),0) AS reviewed_total"""
        + join
        + where
        + " GROUP BY r.category",
        **params,
    )
    return safe(
        {
            "items": items,
            "total": count,
            "limit": limit,
            "offset": offset,
            "summary": totals,
            "submitted_total": sum((r["submitted_total"] for r in totals), Decimal("0.00")),
            "reviewed_total": sum((r["reviewed_total"] for r in totals), Decimal("0.00")),
            "currency": "PHP",
        }
    )


@router.get("/trips/{trip_id}/expenses")
async def list_expenses(
    trip_id: uuid.UUID,
    ctx: Context,
    db: Database,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await trip_access(db, ctx, trip_id)
    return await listing(db, ctx, "e.trip_id=:trip", {"trip": trip_id}, limit, offset)


@router.get("/vehicles/{vehicle_id}/fuel-history")
async def fuel_history(
    vehicle_id: uuid.UUID,
    ctx: Context,
    db: Database,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    ctx.require("fuel.read")
    ctx.require("expenses.read")
    await find(db, ctx, Vehicle, vehicle_id)
    return await listing(
        db,
        ctx,
        "e.vehicle_id=:vehicle AND r.category='FUEL'",
        {"vehicle": vehicle_id},
        limit,
        offset,
    )


async def mutate(identifier, payload, ctx, db, key, action):
    original = await expense(db, ctx, identifier)
    doc = {
        "command": action,
        "expense": str(identifier),
        "payload": payload.model_dump(mode="json"),
    }
    trip, digest, replay = await command(db, ctx, original["trip_id"], action, key, doc)
    if replay:
        return replay
    await writable(db, ctx, trip, payload.expected_version)
    item = await detail(db, ctx, identifier)
    if item["status"] == "VOIDED":
        raise HTTPException(409, "Voided records are read-only.")
    current = item["current"]
    params = dict(id=identifier, org=ctx.organization.id, actor=ctx.user.id)
    if action == "correct":
        await revision(
            db,
            ctx,
            trip,
            identifier,
            item["current_revision"] + 1,
            payload,
            payload.reason,
            item["vehicle_id"],
        )
        sql = "current_revision=current_revision+1,status='SUBMITTED',reviewed_by=NULL,reviewed_at=NULL,review_notes=NULL"
    elif action == "review":
        if item["status"] != "SUBMITTED":
            raise HTTPException(409, "This expense has already been reviewed.")
        if current["category"] == "FUEL":
            ctx.require("fuel.review")
            data = ExpenseInput.model_validate(
                {k: current[k] for k in ExpenseInput.model_fields if k in current}
                | {"amount": None, "expected_version": payload.expected_version}
            )
            await odometer_check(db, ctx, trip, data, item["vehicle_id"])
        sql = (
            "status='REVIEWED',reviewed_by=:actor,reviewed_at=clock_timestamp(),review_notes=:notes"
        )
        params["notes"] = payload.notes
    else:
        sql = "status='VOIDED',voided_by=:actor,voided_at=clock_timestamp(),void_reason=:reason,reviewed_by=NULL,reviewed_at=NULL,review_notes=NULL"
        params["reason"] = payload.reason
    await db.execute(
        text("UPDATE trip_expenses SET " + sql + " WHERE organization_id=:org AND id=:id"), params
    )
    audit(
        db,
        ctx,
        {"correct": "corrected", "review": "reviewed", "void": "voided"}[action],
        trip,
        identifier,
        current["category"],
        current["amount"],
        before={
            k: item[k]
            for k in ("current_revision", "status", "reviewed_at", "reviewed_by", "review_notes")
        },
        after={
            "reason": getattr(payload, "reason", None),
            "review_notes": getattr(payload, "notes", None),
            "new_amount": str(payload.total) if action == "correct" else current["amount"],
            "new_category": payload.category if action == "correct" else current["category"],
        },
    )
    await touch(db, ctx, trip)
    await db.flush()
    result = {"expense": await detail(db, ctx, identifier), "trip_version": trip.version}
    if action == "correct" and payload.category == "FUEL" and current["category"] != "FUEL":
        record(
            db,
            ctx,
            "fuel.corrected",
            "expense",
            identifier,
            {"category": current["category"], "amount": current["amount"]},
            {
                "trip_id": str(trip.id),
                "category": "FUEL",
                "amount": str(payload.total),
                "reason": payload.reason,
            },
        )
    return await finish(db, ctx, trip, "expense_" + action, key, digest, result)


@router.post("/expenses/{identifier}/review")
async def review(
    identifier: uuid.UUID,
    payload: ReviewInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await mutate(identifier, payload, ctx, db, idempotency_key, "review")


@router.post("/expenses/{identifier}/correct")
async def correct(
    identifier: uuid.UUID,
    payload: CorrectionInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await mutate(identifier, payload, ctx, db, idempotency_key, "correct")


@router.post("/expenses/{identifier}/void")
async def void(
    identifier: uuid.UUID,
    payload: VoidInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    return await mutate(identifier, payload, ctx, db, idempotency_key, "void")


@router.post("/expenses/{identifier}/evidence")
async def upload(
    identifier: uuid.UUID,
    request: Request,
    ctx: Context,
    db: Database,
    expected_version: int = Query(ge=1),
    filename: str = Query(min_length=1, max_length=160),
    supersedes_id: uuid.UUID | None = None,
    idempotency_key: uuid.UUID = Header(),
):
    item = await expense(db, ctx, identifier)
    await trip_access(db, ctx, item["trip_id"], "create")
    if ctx.membership.role != "DRIVER":
        ctx.require("evidence.expense.upload")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise HTTPException(413, "Image exceeds 5 MiB.")
        chunks.append(chunk)
    raw = b"".join(chunks)
    doc = {
        "command": "expense_evidence",
        "expense": str(identifier),
        "version": expected_version,
        "filename": filename,
        "supersedes": str(supersedes_id),
        "mime": request.headers.get("content-type", ""),
        "checksum": hashlib.sha256(raw).hexdigest(),
    }
    trip, digest, replay = await command(db, ctx, item["trip_id"], "create", idempotency_key, doc)
    if ctx.membership.role != "DRIVER":
        require_current(ctx, "evidence.expense.upload")
    if replay:
        return replay
    await writable(db, ctx, trip, expected_version)
    item = await expense(db, ctx, identifier)
    if item["status"] != "SUBMITTED":
        raise HTTPException(409, "Receipts can only be added to submitted expenses.")
    count = await db.scalar(
        text("SELECT count(*) FROM expense_evidence WHERE organization_id=:org AND expense_id=:id"),
        {"org": ctx.organization.id, "id": identifier},
    )
    if count >= 12:
        raise HTTPException(409, "This expense has reached its 12-file history limit.")
    data, checksum = await run_in_threadpool(validate_image, raw, filename, doc["mime"])
    if supersedes_id:
        updated = await db.execute(
            text(
                "UPDATE expense_evidence SET status='SUPERSEDED' WHERE organization_id=:org AND expense_id=:expense AND id=:id AND status='ACTIVE'"
            ),
            {"org": ctx.organization.id, "expense": identifier, "id": supersedes_id},
        )
        if updated.rowcount != 1:
            raise HTTPException(409, "Replacement requires an active receipt on this expense.")
        record(
            db,
            ctx,
            "expense_evidence.superseded",
            "expense",
            identifier,
            None,
            {"evidence_id": str(supersedes_id), "trip_id": str(trip.id)},
        )
    evidence_id = uuid.uuid4()
    key = f"{ctx.organization.id.hex}/{evidence_id.hex}.png"
    store = storage()
    db.info.setdefault("uncommitted_evidence", []).append((store, key))
    await run_in_threadpool(store.put, key, data)
    await db.execute(
        text("""INSERT INTO expense_evidence(id,organization_id,trip_id,expense_id,storage_key,original_filename,content_type,file_size,checksum,uploaded_by,supersedes_id)
      VALUES(:id,:org,:trip,:expense,:key,:filename,'image/png',:size,:checksum,:actor,:supersedes)"""),
        dict(
            id=evidence_id,
            org=ctx.organization.id,
            trip=trip.id,
            expense=identifier,
            key=key,
            filename=filename,
            size=len(data),
            checksum=checksum,
            actor=ctx.user.id,
            supersedes=supersedes_id,
        ),
    )
    record(
        db,
        ctx,
        "expense_evidence.uploaded",
        "expense",
        identifier,
        None,
        {"evidence_id": str(evidence_id), "trip_id": str(trip.id)},
    )
    await touch(db, ctx, trip)
    await db.flush()
    return await finish(
        db,
        ctx,
        trip,
        "expense_evidence",
        idempotency_key,
        digest,
        {"evidence_id": str(evidence_id), "trip_version": trip.version},
    )


@router.get("/expense-evidence/{identifier}")
async def retrieve(identifier: uuid.UUID, ctx: Context, db: Database):
    ctx.require(capability(ctx, "read"))
    if ctx.membership.role != "DRIVER":
        ctx.require("evidence.expense.read")
    found = await rows(
        db,
        "SELECT * FROM expense_evidence WHERE organization_id=:org AND id=:id",
        org=ctx.organization.id,
        id=identifier,
    )
    if not found:
        raise HTTPException(404, "Receipt not found.")
    row = found[0]
    await expense(db, ctx, row["expense_id"])
    try:
        data = await run_in_threadpool(storage().read, row["storage_key"])
    except FileNotFoundError as exc:
        raise HTTPException(404, "Receipt unavailable.") from exc
    if hashlib.sha256(data).hexdigest() != row["checksum"]:
        raise HTTPException(503, "Receipt integrity check failed.")
    return Response(
        data,
        media_type="image/png",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'inline; filename="receipt.png"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
