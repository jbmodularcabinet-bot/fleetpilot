"""Driver-only durable command replay. Client ownership claims are never accepted."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text

from . import delivery_routes as delivery
from .delivery_schemas import EvidenceType, ExceptionInput, PODInput
from .master_routes import write_lock
from .trip_routes import own_profile, own_trip, transition
from .trip_schemas import TripTransition, VersionInput

router = APIRouter(prefix="/api/v1/driver", tags=["Driver sync"])
CAPS = {
    "transition": "driver_trip.transition_own",
    "attempt": "driver_pod.submit_own",
    "pod": "driver_pod.submit_own",
    "exception": "driver_exception.create_own",
    "evidence": "driver_evidence.upload_own",
    "expense": "driver_expense.create_own",
}


class SyncInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    occurred_at_client: datetime
    resource_id: uuid.UUID | None = None
    payload: dict = Field(default_factory=dict)


@router.get("/offline-identity")
async def identity(ctx: delivery.Context, db: delivery.Database):
    ctx.require("driver_app.view")
    if ctx.membership.role != "DRIVER":
        raise HTTPException(403, "Offline access is for drivers only.")
    profile = await own_profile(db, ctx)
    return {
        "user_id": str(ctx.user.id),
        "organization_id": str(ctx.organization.id),
        "driver_id": str(profile.id) if profile else None,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "offline_seconds": 43200,
    }


async def begin(db, ctx, trip_id, command, key, document):
    if ctx.membership.role != "DRIVER":
        raise HTTPException(403, "Offline commands are for drivers only.")
    await write_lock(db, ctx, CAPS[command])
    trip = await own_trip(db, ctx, trip_id)
    await db.refresh(trip)
    digest, replay = await receipt(db, ctx, key, document)
    return trip, digest, replay


async def receipt(db, ctx, key, document):
    digest = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    row = (
        (
            await db.execute(
                text("""SELECT request_hash,result FROM driver_sync_commands
        WHERE organization_id=:org AND actor_user_id=:actor AND idempotency_key=:key"""),
                {"org": ctx.organization.id, "actor": ctx.user.id, "key": key},
            )
        )
        .mappings()
        .first()
    )
    if row:
        if row["request_hash"] != digest:
            raise HTTPException(409, "This saved action key was already used for different data.")
        return digest, {"outcome": "ALREADY_APPLIED", "result": row["result"]}
    return digest, None


async def finish(db, ctx, trip, command, key, digest, captured, result):
    if captured.tzinfo is None:
        raise HTTPException(422, "Capture time must include a timezone.")
    suspect = abs((datetime.now(timezone.utc) - captured).total_seconds()) > 86400
    await db.execute(
        text("""INSERT INTO driver_sync_commands
      (organization_id,actor_user_id,idempotency_key,driver_id,trip_id,command_type,
       request_hash,result,occurred_at_client,clock_suspect)
      VALUES (:org,:actor,:key,:driver,:trip,:command,:hash,CAST(:result AS jsonb),:captured,:suspect)"""),
        {
            "org": ctx.organization.id,
            "actor": ctx.user.id,
            "key": key,
            "driver": trip.driver_id,
            "trip": trip.id,
            "command": command,
            "hash": digest,
            "result": json.dumps(result),
            "captured": captured,
            "suspect": suspect,
        },
    )
    await db.commit()
    db.info.pop("uncommitted_evidence", None)
    return {"outcome": "APPLIED", "result": result}


@router.post("/sync/{trip_id}/evidence")
async def sync_evidence(
    trip_id: uuid.UUID,
    request: Request,
    ctx: delivery.Context,
    db: delivery.Database,
    resource_id: uuid.UUID,
    expected_version: int = Query(ge=1),
    occurred_at_client: datetime = Query(),
    filename: str = Query(min_length=1, max_length=160),
    evidence_type: EvidenceType = "DELIVERY_PHOTO",
    idempotency_key: uuid.UUID = Header(),
):
    # Authenticate and authorize BEFORE reading the bounded raw body.
    if ctx.membership.role != "DRIVER":
        raise HTTPException(403, "Driver access required.")
    ctx.require(CAPS["evidence"])
    await own_trip(db, ctx, trip_id)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > delivery.MAX_FILE_BYTES:
            raise HTTPException(413, "Image exceeds 5 MiB.")
    document = {
        "trip": str(trip_id),
        "command": "evidence",
        "resource": str(resource_id),
        "version": expected_version,
        "captured": occurred_at_client.isoformat(),
        "filename": filename,
        "type": evidence_type,
        "mime": request.headers.get("content-type"),
        "bytes": hashlib.sha256(data).hexdigest(),
    }
    trip, digest, replay = await begin(db, ctx, trip_id, "evidence", idempotency_key, document)
    if replay:
        return replay
    attempt = await delivery.find(db, ctx, delivery.DeliveryAttempt, resource_id)
    if attempt.trip_id != trip_id:
        raise HTTPException(404, "Delivery attempt not found.")

    async def receive():
        return {"type": "http.request", "body": bytes(data), "more_body": False}

    db.info["sync_transaction"] = True
    result = await delivery.upload_evidence(
        resource_id,
        Request(request.scope, receive),
        ctx,
        db,
        expected_version,
        evidence_type,
        filename,
        None,
    )
    return await finish(
        db, ctx, trip, "evidence", idempotency_key, digest, occurred_at_client, result
    )


@router.post("/sync/{trip_id}/{command}")
async def sync_command(
    trip_id: uuid.UUID,
    command: Literal["transition", "attempt", "pod", "exception", "expense"],
    payload: SyncInput,
    ctx: delivery.Context,
    db: delivery.Database,
    idempotency_key: uuid.UUID = Header(),
):
    document = {"trip": str(trip_id), "command": command, **payload.model_dump(mode="json")}
    trip, digest, replay = await begin(db, ctx, trip_id, command, idempotency_key, document)
    if replay:
        return replay
    if payload.occurred_at_client.tzinfo is None:
        raise HTTPException(422, "Capture time must include a timezone.")
    body = {**payload.payload, "expected_version": payload.expected_version}
    if "expected_version" in payload.payload:
        raise HTTPException(422, "Version must be specified once.")
    db.info["sync_transaction"] = True
    if command in {"pod", "exception"}:
        attempt = await delivery.find(db, ctx, delivery.DeliveryAttempt, payload.resource_id)
        if attempt.trip_id != trip_id:
            raise HTTPException(404, "Delivery attempt not found.")
    elif payload.resource_id is not None:
        raise HTTPException(422, "Unexpected delivery attempt.")
    try:
        if command == "transition":
            result = await transition(
                trip_id, TripTransition.model_validate(body), ctx, db, own=True
            )
        elif command == "expense":
            from .expense_routes import create
            from .expense_schemas import ExpenseInput

            result = await create(db, ctx, trip, ExpenseInput.model_validate(body))
        elif command == "attempt":
            result = await delivery.create_attempt(
                trip_id, VersionInput.model_validate(body), ctx, db
            )
        elif command == "pod":
            result = await delivery.submit_pod(
                payload.resource_id, PODInput.model_validate(body), ctx, db
            )
        else:
            result = await delivery.fail_attempt(
                payload.resource_id, ExceptionInput.model_validate(body), ctx, db
            )
    except ValidationError as exc:
        raise HTTPException(422, "Check the saved action fields.") from exc
    return await finish(
        db, ctx, trip, command, idempotency_key, digest, payload.occurred_at_client, result
    )
