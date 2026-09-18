"""Authorized delivery commands; all database changes share the trip transaction."""

import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from .audit import record
from .db import get_db
from .delivery_models import DeliveryAttempt, DeliveryEvidence, DeliveryException, ProofOfDelivery
from .delivery_policy import DELIVERY_STAGES, MAX_ATTEMPT_FILES, MAX_FILE_BYTES, POLICY
from .delivery_schemas import EvidenceType, ExceptionInput, PODInput, ResolveInput
from .evidence_storage import storage, validate_image
from .master_routes import find, require_current, scoped, write_lock
from .tenancy import TenantContext, tenant
from .trip_models import Trip
from .trip_routes import event, fields, now, own_trip, touch, trip_view, version_check
from .trip_schemas import VersionInput

router = APIRouter(prefix="/api/v1", tags=["Delivery evidence"])
Context = Annotated[TenantContext, Depends(tenant)]
Database = Annotated[AsyncSession, Depends(get_db)]


async def committed(db, result):
    # FastAPI request-scoped yield cleanup may run after the response starts.
    # Delivery commands must observe commit/constraint errors before reporting success.
    if db.info.get("sync_transaction"):
        await db.flush()
        return result
    await db.commit()
    db.info.pop("uncommitted_evidence", None)
    return result


def permission(ctx, owner, driver):
    return driver if ctx.membership.role == "DRIVER" else owner


async def access_trip(db, ctx, trip_id):
    if ctx.membership.role == "DRIVER":
        return await own_trip(db, ctx, trip_id)
    ctx.require("trips.read")
    return await find(db, ctx, Trip, trip_id)


async def command(db, ctx, trip_id, version, owner, driver):
    await write_lock(db, ctx, permission(ctx, owner, driver))
    trip = await access_trip(db, ctx, trip_id)
    await db.refresh(
        trip
    )  # Upload authorization may have populated the identity map before locking.
    version_check(trip, version)
    return trip


def audit(db, ctx, action, trip, attempt_id, entity_id):
    record(
        db,
        ctx,
        action,
        "trip",
        trip.id,
        None,
        {"delivery_attempt_id": str(attempt_id), "record_id": str(entity_id)},
    )


async def latest_attempt(db, ctx, trip):
    return await db.scalar(
        scoped(DeliveryAttempt, ctx)
        .where(DeliveryAttempt.trip_id == trip.id)
        .order_by(DeliveryAttempt.attempt_number.desc())
        .limit(1)
    )


async def unresolved(db, ctx, trip):
    return await db.scalar(
        scoped(DeliveryException, ctx)
        .where(DeliveryException.trip_id == trip.id, DeliveryException.status == "OPEN")
        .limit(1)
    )


async def assert_delivery_open(db, ctx, trip):
    if trip.current_milestone not in DELIVERY_STAGES:
        raise HTTPException(
            409, "Delivery evidence is available after arrival and before delivery confirmation."
        )
    if await unresolved(db, ctx, trip):
        raise HTTPException(
            409, "An operator must resolve the delivery issue and authorize a retry."
        )


async def open_attempt(db, ctx, trip, identifier):
    attempt = await find(db, ctx, DeliveryAttempt, identifier)
    if attempt.trip_id != trip.id or attempt.status != "IN_PROGRESS":
        raise HTTPException(409, "This delivery attempt is closed.")
    await assert_delivery_open(db, ctx, trip)
    return attempt


def evidence_view(row):
    return {key: value for key, value in fields(row).items() if key != "storage_key"}


async def attempt_view(db, ctx, row):
    data = fields(row)
    pod = await db.scalar(
        scoped(ProofOfDelivery, ctx).where(ProofOfDelivery.delivery_attempt_id == row.id)
    )
    issue = await db.scalar(
        scoped(DeliveryException, ctx).where(DeliveryException.delivery_attempt_id == row.id)
    )
    data["pod"] = fields(pod) if pod else None
    data["exception"] = fields(issue) if issue else None
    cap = permission(ctx, "delivery_evidence.read", "driver_evidence.read_own")
    data["evidence"] = (
        [
            evidence_view(item)
            for item in (
                await db.scalars(
                    scoped(DeliveryEvidence, ctx)
                    .where(DeliveryEvidence.delivery_attempt_id == row.id)
                    .order_by(DeliveryEvidence.uploaded_at)
                )
            ).all()
        ]
        if cap in ctx.permissions
        else []
    )
    return jsonable_encoder(data)


@router.get("/trips/{trip_id}/delivery-attempts")
async def list_attempts(
    trip_id: uuid.UUID,
    ctx: Context,
    db: Database,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    ctx.require(permission(ctx, "pod.read", "driver_pod.read_own"))
    if ctx.membership.role != "DRIVER":
        ctx.require("delivery_exception.read")
    trip = await access_trip(db, ctx, trip_id)
    query = scoped(DeliveryAttempt, ctx).where(DeliveryAttempt.trip_id == trip.id)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(
            query.order_by(DeliveryAttempt.attempt_number.desc()).limit(limit).offset(offset)
        )
    ).all()
    return {
        "items": [await attempt_view(db, ctx, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "trip_version": trip.version,
        "policy": POLICY,
        "legacy_delivery": not trip.pod_required,
    }


@router.get("/delivery-attempts/{identifier}")
async def get_attempt(identifier: uuid.UUID, ctx: Context, db: Database):
    ctx.require(permission(ctx, "pod.read", "driver_pod.read_own"))
    if ctx.membership.role != "DRIVER":
        ctx.require("delivery_exception.read")
    row = await find(db, ctx, DeliveryAttempt, identifier)
    await access_trip(db, ctx, row.trip_id)
    return await attempt_view(db, ctx, row)


@router.post("/trips/{trip_id}/delivery-attempts", status_code=201)
async def create_attempt(trip_id: uuid.UUID, payload: VersionInput, ctx: Context, db: Database):
    trip = await command(
        db, ctx, trip_id, payload.expected_version, "pod.submit", "driver_pod.submit_own"
    )
    await assert_delivery_open(db, ctx, trip)
    previous = await latest_attempt(db, ctx, trip)
    if previous and previous.status != "FAILED":
        raise HTTPException(409, "Use the existing delivery attempt.")
    stamp = await now(db)
    attempt = DeliveryAttempt(
        organization_id=ctx.organization.id,
        trip_id=trip.id,
        attempt_number=previous.attempt_number + 1 if previous else 1,
        arrived_at=stamp,
        created_at=stamp,
        created_by=ctx.user.id,
    )
    db.add(attempt)
    await touch(db, ctx, trip)
    await db.flush()
    if previous:
        await event(db, ctx, trip, "DELIVERY_RETRY_STARTED", own=ctx.membership.role == "DRIVER")
    audit(db, ctx, "delivery_attempt.created", trip, attempt.id, attempt.id)
    return await committed(
        db, {"attempt": await attempt_view(db, ctx, attempt), "trip_version": trip.version}
    )


@router.post("/delivery-attempts/{identifier}/evidence", status_code=201)
async def upload_evidence(
    identifier: uuid.UUID,
    request: Request,
    ctx: Context,
    db: Database,
    expected_version: int = Query(ge=1),
    evidence_type: EvidenceType = "DELIVERY_PHOTO",
    filename: str = Query(min_length=1, max_length=160),
    supersedes_id: uuid.UUID | None = None,
):
    cap = permission(ctx, "delivery_evidence.upload", "driver_evidence.upload_own")
    ctx.require(cap)
    initial = await find(db, ctx, DeliveryAttempt, identifier)
    await access_trip(db, ctx, initial.trip_id)
    # Raw image body avoids parsing an unbounded multipart body into temporary files.
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise HTTPException(413, "Image exceeds 5 MiB.")
        chunks.append(chunk)
    data, checksum = await run_in_threadpool(
        validate_image, b"".join(chunks), filename, request.headers.get("content-type", "")
    )
    trip = await command(
        db,
        ctx,
        initial.trip_id,
        expected_version,
        "delivery_evidence.upload",
        "driver_evidence.upload_own",
    )
    await db.refresh(initial)
    await open_attempt(db, ctx, trip, identifier)
    count = await db.scalar(
        select(func.count())
        .select_from(DeliveryEvidence)
        .where(
            DeliveryEvidence.organization_id == ctx.organization.id,
            DeliveryEvidence.delivery_attempt_id == identifier,
        )
    )
    if count >= MAX_ATTEMPT_FILES:
        raise HTTPException(409, "This attempt has reached its 12-file history limit.")
    if supersedes_id:
        previous = await find(db, ctx, DeliveryEvidence, supersedes_id)
        if (
            previous.delivery_attempt_id != identifier
            or previous.status != "ACTIVE"
            or previous.evidence_type != evidence_type
        ):
            raise HTTPException(
                409, "Replacement must target active evidence of the same type in this attempt."
            )
        previous.status = "SUPERSEDED"
        await db.flush()
        audit(db, ctx, "evidence.superseded", trip, identifier, previous.id)
    identifier_new = uuid.uuid4()
    key = f"{ctx.organization.id.hex}/{identifier_new.hex}.png"
    store = storage()
    # Register before writing so failures during a write are also compensated.
    db.info.setdefault("uncommitted_evidence", []).append((store, key))
    await run_in_threadpool(store.put, key, data)
    row = DeliveryEvidence(
        id=identifier_new,
        organization_id=ctx.organization.id,
        trip_id=trip.id,
        delivery_attempt_id=identifier,
        evidence_type=evidence_type,
        storage_key=key,
        original_filename=filename,
        content_type="image/png",
        file_size=len(data),
        checksum=checksum,
        uploaded_at=await now(db),
        uploaded_by=ctx.user.id,
        supersedes_id=supersedes_id,
    )
    db.add(row)
    await touch(db, ctx, trip)
    await db.flush()
    audit(db, ctx, "evidence.uploaded", trip, identifier, row.id)
    return await committed(
        db, {"evidence": jsonable_encoder(evidence_view(row)), "trip_version": trip.version}
    )


@router.get("/evidence/{identifier}")
async def retrieve_evidence(identifier: uuid.UUID, ctx: Context, db: Database):
    ctx.require(permission(ctx, "delivery_evidence.read", "driver_evidence.read_own"))
    row = await find(db, ctx, DeliveryEvidence, identifier)
    await access_trip(db, ctx, row.trip_id)
    try:
        data = await run_in_threadpool(storage().read, row.storage_key)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, "Evidence file is unavailable.") from exc
    if hashlib.sha256(data).hexdigest() != row.checksum:
        raise HTTPException(503, "Evidence integrity verification failed.")
    return Response(
        data,
        media_type=row.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'inline; filename="delivery-evidence.png"',
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/evidence/{identifier}/metadata")
async def read_evidence_metadata(identifier: uuid.UUID, ctx: Context, db: Database):
    ctx.require(permission(ctx, "delivery_evidence.read", "driver_evidence.read_own"))
    row = await find(db, ctx, DeliveryEvidence, identifier)
    await access_trip(db, ctx, row.trip_id)
    return jsonable_encoder(evidence_view(row))


@router.get("/delivery-exceptions/{identifier}")
async def read_exception(identifier: uuid.UUID, ctx: Context, db: Database):
    ctx.require(permission(ctx, "delivery_exception.read", "driver_pod.read_own"))
    row = await find(db, ctx, DeliveryException, identifier)
    await access_trip(db, ctx, row.trip_id)
    return jsonable_encoder(fields(row))


@router.post("/delivery-attempts/{identifier}/pod", status_code=201)
async def submit_pod(identifier: uuid.UUID, payload: PODInput, ctx: Context, db: Database):
    initial = await find(db, ctx, DeliveryAttempt, identifier)
    trip = await command(
        db, ctx, initial.trip_id, payload.expected_version, "pod.submit", "driver_pod.submit_own"
    )
    require_current(ctx, permission(ctx, "trips.transition", "driver_trip.transition_own"))
    attempt = await open_attempt(db, ctx, trip, identifier)
    if trip.current_milestone != "UNLOADING_COMPLETED":
        raise HTTPException(409, "Complete unloading before confirming delivery.")
    evidence = (
        await db.scalars(
            scoped(DeliveryEvidence, ctx).where(
                DeliveryEvidence.delivery_attempt_id == identifier,
                DeliveryEvidence.status == "ACTIVE",
            )
        )
    ).all()
    if (
        sum(item.evidence_type == "DELIVERY_PHOTO" for item in evidence)
        < POLICY["minimum_delivery_photos"]
    ):
        raise HTTPException(422, "At least one delivery photo is required.")
    signature = next((item for item in evidence if item.evidence_type == "SIGNATURE"), None)
    if POLICY["signature_required"] and not signature:
        raise HTTPException(422, "A recipient signature is required by the evidence policy.")
    if signature and not payload.signature_confirmed:
        raise HTTPException(422, "Confirm the recipient signature before submission.")
    # Verify stored bytes before committing delivery; missing/corrupt objects cannot become POD.
    for item in evidence:
        try:
            raw = await run_in_threadpool(storage().read, item.storage_key)
        except (OSError, ValueError) as exc:
            raise HTTPException(
                409, "An evidence file is unavailable. Contact your operator."
            ) from exc
        if hashlib.sha256(raw).hexdigest() != item.checksum:
            raise HTTPException(409, "Evidence integrity check failed.")
    stamp = await now(db)
    pod = ProofOfDelivery(
        organization_id=ctx.organization.id,
        trip_id=trip.id,
        delivery_attempt_id=identifier,
        recipient_name=payload.recipient_name,
        recipient_role=payload.recipient_role,
        confirmed_at=stamp,
        confirmed_by_driver_id=trip.driver_id,
        confirmed_by_user_id=ctx.user.id,
        driver_confirmed=True,
        signature_evidence_id=signature.id if signature else None,
        notes=payload.notes,
    )
    db.add(pod)
    attempt.status, attempt.completed_at = "DELIVERED", stamp
    await db.flush()
    # The only normal entry point to DELIVERED. Audits, POD, attempt, trip and milestone commit together.
    await touch(db, ctx, trip)
    trip.current_status = trip.current_milestone = "DELIVERED"
    await db.flush()
    await event(db, ctx, trip, "DELIVERED", own=ctx.membership.role == "DRIVER")
    for action, entity in [
        ("delivery_attempt.delivered", attempt.id),
        ("pod.submitted", pod.id),
        ("trip.delivered", trip.id),
    ]:
        audit(db, ctx, action, trip, identifier, entity)
    return await committed(
        db,
        {
            "pod": jsonable_encoder(fields(pod)),
            "trip": await trip_view(db, ctx, trip, ctx.membership.role == "DRIVER"),
        },
    )


@router.get("/pod/{identifier}")
async def read_pod(identifier: uuid.UUID, ctx: Context, db: Database):
    ctx.require(permission(ctx, "pod.read", "driver_pod.read_own"))
    pod = await find(db, ctx, ProofOfDelivery, identifier)
    await access_trip(db, ctx, pod.trip_id)
    return jsonable_encoder(fields(pod))


@router.post("/pod/{identifier}/review")
async def review_pod(identifier: uuid.UUID, payload: VersionInput, ctx: Context, db: Database):
    await write_lock(db, ctx, "pod.review")
    pod = await find(db, ctx, ProofOfDelivery, identifier)
    trip = await access_trip(db, ctx, pod.trip_id)
    version_check(trip, payload.expected_version)
    if pod.status != "SUBMITTED" or trip.current_status != "DELIVERED":
        raise HTTPException(409, "This POD is not awaiting review.")
    pod.status, pod.reviewed_at, pod.reviewed_by = "REVIEWED", await now(db), ctx.user.id
    await touch(db, ctx, trip)
    audit(db, ctx, "pod.reviewed", trip, pod.delivery_attempt_id, pod.id)
    await db.flush()
    return await committed(db, {"pod": jsonable_encoder(fields(pod)), "trip_version": trip.version})


@router.post("/delivery-attempts/{identifier}/exception", status_code=201)
async def fail_attempt(identifier: uuid.UUID, payload: ExceptionInput, ctx: Context, db: Database):
    initial = await find(db, ctx, DeliveryAttempt, identifier)
    trip = await command(
        db,
        ctx,
        initial.trip_id,
        payload.expected_version,
        "delivery_exception.create",
        "driver_exception.create_own",
    )
    attempt = await open_attempt(db, ctx, trip, identifier)
    stamp = await now(db)
    issue = DeliveryException(
        organization_id=ctx.organization.id,
        trip_id=trip.id,
        delivery_attempt_id=identifier,
        exception_type=payload.exception_type,
        notes=payload.notes,
        created_by=ctx.user.id,
        created_at=stamp,
    )
    db.add(issue)
    attempt.status, attempt.completed_at = "FAILED", stamp
    await touch(db, ctx, trip)
    await db.flush()
    await event(db, ctx, trip, "DELIVERY_ATTEMPT_FAILED", own=ctx.membership.role == "DRIVER")
    for action in ("delivery_attempt.failed", "delivery_exception.created"):
        audit(db, ctx, action, trip, identifier, issue.id)
    return await committed(
        db, {"exception": jsonable_encoder(fields(issue)), "trip_version": trip.version}
    )


@router.post("/delivery-exceptions/{identifier}/resolve")
async def resolve_exception(
    identifier: uuid.UUID, payload: ResolveInput, ctx: Context, db: Database
):
    await write_lock(db, ctx, "delivery_exception.resolve")
    issue = await find(db, ctx, DeliveryException, identifier)
    trip = await access_trip(db, ctx, issue.trip_id)
    version_check(trip, payload.expected_version)
    if issue.status != "OPEN" or trip.current_milestone not in DELIVERY_STAGES:
        raise HTTPException(409, "This exception cannot be retried.")
    issue.status, issue.resolved_at, issue.resolved_by, issue.resolution_notes = (
        "RETRY_AUTHORIZED",
        await now(db),
        ctx.user.id,
        payload.resolution_notes,
    )
    await touch(db, ctx, trip)
    await event(db, ctx, trip, "DELIVERY_RETRY_AUTHORIZED")
    audit(db, ctx, "delivery_exception.resolved", trip, issue.delivery_attempt_id, issue.id)
    await db.flush()
    return await committed(
        db, {"exception": jsonable_encoder(fields(issue)), "trip_version": trip.version}
    )
