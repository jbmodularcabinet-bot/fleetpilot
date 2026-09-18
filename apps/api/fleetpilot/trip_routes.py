import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .audit import record
from .db import get_db
from .master_models import Customer, Driver, Vehicle
from .master_routes import find, require_current, scoped, search_pattern, write_lock
from .tenancy import TenantContext, tenant
from .trip_lifecycle import ACTIONS, STATUS, TERMINAL, next_action
from .trip_models import Trip, TripAssignment, TripMilestone
from .trip_schemas import (
    TripAssign,
    TripCancel,
    TripComplete,
    TripCreate,
    TripNotes,
    TripTransition,
    TripUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["Dispatch & trips"])


async def now(db):
    return await db.scalar(select(func.clock_timestamp()))


def fields(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def version_check(row, expected):
    if row.version != expected:
        raise HTTPException(409, "This trip changed. Refresh before trying again.")
    if row.current_status in TERMINAL:
        raise HTTPException(409, "This trip is closed and read-only.")


async def own_profile(db, ctx):
    return await db.scalar(
        scoped(Driver, ctx).where(
            Driver.user_id == ctx.user.id, Driver.employment_status == "ACTIVE"
        )
    )


async def own_trip(db, ctx, identifier):
    ctx.require("driver_trip.read_own")
    profile = await own_profile(db, ctx)
    row = (
        await db.scalar(
            scoped(Trip, ctx).where(
                Trip.id == identifier, Trip.driver_id == (profile.id if profile else None)
            )
        )
        if profile
        else None
    )
    if row is None:
        raise HTTPException(404, "Trip not found.")
    return row


async def trip_view(db, ctx, row, own=False):
    await db.refresh(row)
    customer = await find(db, ctx, Customer, row.customer_id)
    vehicle = await find(db, ctx, Vehicle, row.vehicle_id) if row.vehicle_id else None
    driver = await find(db, ctx, Driver, row.driver_id) if row.driver_id else None
    data = fields(row)
    if own:
        # Deliberate projection: no dispatcher notes, actor IDs, customer references or cancellation details.
        allowed = {
            "id",
            "trip_number",
            "version",
            "pickup_name",
            "pickup_address",
            "pickup_contact_name",
            "pickup_contact_phone",
            "delivery_name",
            "delivery_address",
            "delivery_contact_name",
            "delivery_contact_phone",
            "scheduled_pickup_at",
            "scheduled_delivery_at",
            "current_status",
            "current_milestone",
            "special_instructions",
            "cargo_description",
            "cargo_weight",
            "cargo_weight_unit",
            "completed_at",
        }
        data = {key: value for key, value in data.items() if key in allowed}
    action = next_action(row.current_milestone)
    if action == "deliver":
        action = None  # Batch 5 confirmation is exclusively the evidence-backed POD command.
    from .delivery_models import DeliveryException, ProofOfDelivery

    if await db.scalar(
        scoped(DeliveryException, ctx)
        .where(DeliveryException.trip_id == row.id, DeliveryException.status == "OPEN")
        .limit(1)
    ):
        action = None
    pod = await db.scalar(scoped(ProofOfDelivery, ctx).where(ProofOfDelivery.trip_id == row.id))
    data["pod_status"] = pod.status if pod else None
    data["pod_required"] = row.pod_required
    permission = (
        "driver_trip.transition_own"
        if own
        else "trips.dispatch"
        if action == "dispatch"
        else "trips.transition"
    )
    if (
        (own and action == "dispatch")
        or permission not in ctx.permissions
        or not row.vehicle_id
        or not row.driver_id
    ):
        action = None
    data.update(
        customer_name=customer.company_name,
        vehicle_unit=vehicle.unit_number if vehicle else None,
        vehicle_plate=vehicle.plate_number if vehicle else None,
        driver_name=f"{driver.first_name} {driver.last_name}" if driver else None,
        next_action=action,
        next_action_label=ACTIONS[action][2] if action else None,
    )
    return jsonable_encoder(data)


async def eligible(db, ctx, customer_id, vehicle_id=None, driver_id=None):
    customer = await find(db, ctx, Customer, customer_id)
    if customer.status != "ACTIVE":
        raise HTTPException(409, "Select an active customer.")
    if vehicle_id:
        vehicle = await find(db, ctx, Vehicle, vehicle_id)
        driver = await find(db, ctx, Driver, driver_id)
        if vehicle.status in ("INACTIVE", "MAINTENANCE") or driver.employment_status != "ACTIVE":
            raise HTTPException(409, "Select an active vehicle and driver.")


async def conflicts(db, ctx, row, vehicle_id, driver_id, dispatch=False):
    if not vehicle_id:
        return
    end = row.scheduled_delivery_at or row.scheduled_pickup_at + timedelta(hours=24)
    others = (
        await db.scalars(
            scoped(Trip, ctx).where(
                Trip.id != row.id,
                Trip.current_status.not_in(TERMINAL),
                or_(Trip.vehicle_id == vehicle_id, Trip.driver_id == driver_id),
            )
        )
    ).all()
    for other in others:
        other_end = other.scheduled_delivery_at or other.scheduled_pickup_at + timedelta(hours=24)
        if (dispatch and other.current_status != "SCHEDULED") or (
            row.scheduled_pickup_at < other_end and other.scheduled_pickup_at < end
        ):
            raise HTTPException(
                409, "Vehicle or driver has a conflicting trip. Adjust the schedule or assignment."
            )


async def event(db, ctx, row, milestone, notes=None, own=False):
    number = (
        await db.scalar(
            select(func.max(TripMilestone.event_number)).where(
                TripMilestone.organization_id == ctx.organization.id,
                TripMilestone.trip_id == row.id,
            )
        )
        or 0
    ) + 1
    stamp = await now(db)
    db.add(
        TripMilestone(
            organization_id=ctx.organization.id,
            trip_id=row.id,
            event_number=number,
            milestone_type=milestone,
            occurred_at=stamp,
            recorded_at=stamp,
            recorded_by=ctx.user.id,
            source="DRIVER_APP"
            if own
            else "DISPATCHER_WEB"
            if ctx.membership.role == "DISPATCHER"
            else "OWNER_WEB",
            notes=notes,
            metadata_json={"trip_version": row.version},
        )
    )
    await db.flush()


async def touch(db, ctx, row):
    row.version += 1
    row.updated_by, row.updated_at = ctx.user.id, await now(db)


async def close_assignment(db, ctx, row):
    active = await db.scalar(
        scoped(TripAssignment, ctx).where(
            TripAssignment.trip_id == row.id, TripAssignment.is_current.is_(True)
        )
    )
    if active:
        active.is_current, active.ended_at = False, await now(db)
        await db.flush()


async def assign(db, ctx, row, vehicle_id, driver_id):
    await eligible(db, ctx, row.customer_id, vehicle_id, driver_id)
    await conflicts(
        db, ctx, row, vehicle_id, driver_id, dispatch=row.current_status == "DISPATCHED"
    )
    previous = {
        "vehicle_id": str(row.vehicle_id) if row.vehicle_id else None,
        "driver_id": str(row.driver_id) if row.driver_id else None,
    }
    if row.vehicle_id == vehicle_id and row.driver_id == driver_id:
        raise HTTPException(409, "This vehicle and driver are already assigned.")
    await close_assignment(db, ctx, row)
    row.vehicle_id, row.driver_id = vehicle_id, driver_id
    db.add(
        TripAssignment(
            organization_id=ctx.organization.id,
            trip_id=row.id,
            vehicle_id=vehicle_id,
            driver_id=driver_id,
            created_by=ctx.user.id,
        )
    )
    record(
        db,
        ctx,
        "trip.reassigned" if previous["vehicle_id"] else "trip.assigned",
        "trip",
        row.id,
        previous,
        {"vehicle_id": str(vehicle_id), "driver_id": str(driver_id)},
    )


@router.post("/trips", status_code=201)
async def create_trip(
    payload: TripCreate, ctx: TenantContext = Depends(tenant), db: AsyncSession = Depends(get_db)
):
    await write_lock(db, ctx, "trips.create")
    if payload.vehicle_id:
        require_current(ctx, "trips.assign")
        require_current(ctx, "dispatch.manage")
    await eligible(db, ctx, payload.customer_id, payload.vehicle_id, payload.driver_id)
    sequence = (
        await db.scalar(
            select(func.max(Trip.number_sequence)).where(
                Trip.organization_id == ctx.organization.id
            )
        )
        or 0
    ) + 1
    stamp = await now(db)
    row = Trip(
        **payload.model_dump(exclude={"vehicle_id", "driver_id"}),
        organization_id=ctx.organization.id,
        trip_number=f"TRIP-{stamp.astimezone(ZoneInfo(ctx.organization.timezone)).year}-{sequence:06d}",
        number_sequence=sequence,
        created_by=ctx.user.id,
        updated_by=ctx.user.id,
    )
    db.add(row)
    await db.flush()
    if payload.vehicle_id:
        await assign(db, ctx, row, payload.vehicle_id, payload.driver_id)
    await event(db, ctx, row, "TRIP_CREATED")
    await event(db, ctx, row, "SCHEDULED")
    record(
        db,
        ctx,
        "trip.created",
        "trip",
        row.id,
        None,
        {"trip_number": row.trip_number, "status": "SCHEDULED"},
    )
    await db.flush()
    return await trip_view(db, ctx, row)


@router.get("/dispatch")
@router.get("/trips")
async def list_trips(
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db),
    view: Literal["all", "today", "upcoming", "active", "closed", "cancelled"] = "all",
    search: str = Query("", max_length=160),
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
    customer_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: Literal[
        "scheduled_pickup_at",
        "scheduled_delivery_at",
        "trip_number",
        "current_status",
        "created_at",
    ] = "scheduled_pickup_at",
    direction: Literal["asc", "desc"] = "asc",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
):
    ctx.require("trips.read")
    ctx.require("dispatch.read")
    query = (
        scoped(Trip, ctx)
        .join(Customer, Customer.id == Trip.customer_id)
        .where(Customer.organization_id == ctx.organization.id)
    )
    for model, value, column in (
        (Customer, customer_id, Trip.customer_id),
        (Vehicle, vehicle_id, Trip.vehicle_id),
        (Driver, driver_id, Trip.driver_id),
    ):
        if value:
            await find(db, ctx, model, value)
            query = query.where(column == value)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "Start date must not follow end date.")
    zone = ZoneInfo(ctx.organization.timezone)
    today = datetime.now(timezone.utc).astimezone(zone).date()
    if view == "today":
        query = query.where(
            Trip.scheduled_pickup_at >= datetime.combine(today, time.min, zone),
            Trip.scheduled_pickup_at < datetime.combine(today + timedelta(days=1), time.min, zone),
        )
    elif view == "upcoming":
        query = query.where(
            Trip.current_status == "SCHEDULED",
            Trip.scheduled_pickup_at >= datetime.combine(today + timedelta(days=1), time.min, zone),
        )
    elif view == "active":
        query = query.where(
            Trip.current_status.in_(["DISPATCHED", "PICKUP", "LOADED", "IN_TRANSIT"])
        )
    elif view == "closed":
        query = query.where(Trip.current_status.in_(["DELIVERED", "COMPLETED"]))
    elif view == "cancelled":
        query = query.where(Trip.current_status == "CANCELLED")
    if status:
        query = query.where(Trip.current_status == status)
    if date_from:
        query = query.where(Trip.scheduled_pickup_at >= datetime.combine(date_from, time.min, zone))
    if date_to:
        query = query.where(
            Trip.scheduled_pickup_at < datetime.combine(date_to + timedelta(days=1), time.min, zone)
        )
    if search.strip():
        pattern = search_pattern(search.strip())
        query = query.where(
            or_(
                *(
                    column.ilike(pattern, escape="\\")
                    for column in (
                        Trip.trip_number,
                        Customer.company_name,
                        Trip.pickup_name,
                        Trip.delivery_name,
                        Trip.reference_number,
                        Trip.customer_reference,
                    )
                )
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    column = getattr(Trip, sort)
    rows = (
        await db.scalars(
            query.order_by(column.asc() if direction == "asc" else column.desc(), Trip.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {
        "items": [await trip_view(db, ctx, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/trips/{identifier}")
async def read_trip(
    identifier: uuid.UUID, ctx: TenantContext = Depends(tenant), db: AsyncSession = Depends(get_db)
):
    ctx.require("trips.read")
    return await trip_view(db, ctx, await find(db, ctx, Trip, identifier))


@router.patch("/trips/{identifier}")
async def update_trip(
    identifier: uuid.UUID,
    payload: TripUpdate,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db),
):
    await write_lock(db, ctx, "trips.update")
    row = await find(db, ctx, Trip, identifier)
    version_check(row, payload.expected_version)
    if row.current_status != "SCHEDULED":
        raise HTTPException(409, "Operational fields can only be edited before dispatch.")
    await eligible(db, ctx, payload.customer_id, row.vehicle_id, row.driver_id)
    changes = {
        key: value
        for key, value in payload.model_dump(exclude={"expected_version"}).items()
        if getattr(row, key) != value
    }
    for key, value in changes.items():
        setattr(row, key, value)
    await conflicts(db, ctx, row, row.vehicle_id, row.driver_id)
    await touch(db, ctx, row)
    record(
        db,
        ctx,
        "trip.updated",
        "trip",
        row.id,
        None,
        {"fields": sorted(changes), "version": row.version},
    )
    await db.flush()
    return await trip_view(db, ctx, row)


@router.patch("/trips/{identifier}/notes")
async def update_notes(
    identifier: uuid.UUID,
    payload: TripNotes,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db),
):
    await write_lock(db, ctx, "trips.update")
    row = await find(db, ctx, Trip, identifier)
    version_check(row, payload.expected_version)
    row.dispatcher_notes = payload.dispatcher_notes
    await touch(db, ctx, row)
    record(
        db,
        ctx,
        "trip.updated",
        "trip",
        row.id,
        None,
        {"fields": ["dispatcher_notes"], "version": row.version},
    )
    await db.flush()
    return await trip_view(db, ctx, row)


@router.post("/trips/{identifier}/assign")
async def assign_trip(
    identifier: uuid.UUID,
    payload: TripAssign,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db),
):
    await write_lock(db, ctx, "trips.assign")
    require_current(ctx, "dispatch.manage")
    row = await find(db, ctx, Trip, identifier)
    version_check(row, payload.expected_version)
    if row.current_milestone not in {"SCHEDULED", "DISPATCHED"}:
        raise HTTPException(409, "Reassignment is only available before travel to pickup starts.")
    await touch(db, ctx, row)
    await assign(db, ctx, row, payload.vehicle_id, payload.driver_id)
    await db.flush()
    return await trip_view(db, ctx, row)


async def transition(identifier, payload, ctx, db, own=False):
    permission = (
        "driver_trip.transition_own"
        if own
        else "trips.dispatch"
        if payload.action == "dispatch"
        else "trips.transition"
    )
    await write_lock(db, ctx, permission)
    row = await own_trip(db, ctx, identifier) if own else await find(db, ctx, Trip, identifier)
    version_check(row, payload.expected_version)
    before, milestones, _ = ACTIONS[payload.action]
    if payload.action == "deliver":
        raise HTTPException(
            409,
            "Confirm delivery with recipient details, driver confirmation and delivery evidence.",
        )
    from .delivery_routes import unresolved

    if await unresolved(db, ctx, row):
        raise HTTPException(409, "An operator must authorize a delivery retry before continuing.")
    if own and payload.action == "dispatch":
        raise HTTPException(403, "Dispatch must be confirmed by your operator.")
    if row.current_milestone != before:
        raise HTTPException(409, "This action is not valid for the trip's current milestone.")
    if not row.vehicle_id or not row.driver_id:
        raise HTTPException(409, "Assign a vehicle and driver before dispatch.")
    await eligible(db, ctx, row.customer_id, row.vehicle_id, row.driver_id)
    if payload.action == "dispatch":
        require_current(ctx, "dispatch.manage")
        await conflicts(db, ctx, row, row.vehicle_id, row.driver_id, dispatch=True)
    await touch(db, ctx, row)
    row.current_milestone = milestones[-1]
    row.current_status = STATUS[row.current_milestone]
    await db.flush()
    for milestone in milestones:
        await event(db, ctx, row, milestone, payload.notes, own)
    action = (
        "trip.dispatched"
        if payload.action == "dispatch"
        else "trip.delivered"
        if payload.action == "deliver"
        else "trip.transitioned"
    )
    record(
        db,
        ctx,
        action,
        "trip",
        row.id,
        {"milestone": before},
        {"milestone": row.current_milestone, "status": row.current_status, "version": row.version},
    )
    await db.flush()
    return await trip_view(db, ctx, row, own)


@router.post("/trips/{identifier}/transition")
async def owner_transition(
    identifier: uuid.UUID,
    payload: TripTransition,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db),
):
    return await transition(identifier, payload, ctx, db)


@router.post("/trips/{identifier}/cancel")
async def cancel_trip(
    identifier: uuid.UUID,
    payload: TripCancel,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db),
):
    await write_lock(db, ctx, "trips.cancel")
    row = await find(db, ctx, Trip, identifier)
    version_check(row, payload.expected_version)
    if row.current_status == "DELIVERED":
        raise HTTPException(
            409, "Delivered trips require closeout; delivery reversal is not supported."
        )
    before = row.current_status
    await touch(db, ctx, row)
    row.current_status = row.current_milestone = "CANCELLED"
    row.cancelled_at, row.cancelled_by, row.cancellation_reason = (
        await now(db),
        ctx.user.id,
        payload.reason,
    )
    await db.flush()
    await close_assignment(db, ctx, row)
    await event(db, ctx, row, "CANCELLED", payload.reason)
    record(
        db,
        ctx,
        "trip.cancelled",
        "trip",
        row.id,
        {"status": before},
        {"status": "CANCELLED", "reason_recorded": True},
    )
    await db.flush()
    return await trip_view(db, ctx, row)


@router.post("/trips/{identifier}/complete")
async def complete_trip(
    identifier: uuid.UUID,
    payload: TripComplete,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db),
):
    await write_lock(db, ctx, "trips.complete")
    row = await find(db, ctx, Trip, identifier)
    version_check(row, payload.expected_version)
    if row.current_status != "DELIVERED":
        raise HTTPException(409, "Confirm delivery before reviewing and completing this trip.")
    if row.pod_required:
        from .delivery_models import ProofOfDelivery

        pod = await db.scalar(scoped(ProofOfDelivery, ctx).where(ProofOfDelivery.trip_id == row.id))
        if not pod or pod.status != "REVIEWED":
            raise HTTPException(409, "Review the proof of delivery before completing this trip.")
    await touch(db, ctx, row)
    row.current_status = row.current_milestone = "COMPLETED"
    row.completed_at = await now(db)
    await db.flush()
    await close_assignment(db, ctx, row)
    await event(db, ctx, row, "COMPLETED", payload.notes)
    record(
        db,
        ctx,
        "trip.completed",
        "trip",
        row.id,
        {"status": "DELIVERED"},
        {"status": "COMPLETED", "closeout_reviewed": True},
    )
    await db.flush()
    return await trip_view(db, ctx, row)


async def milestones(db, ctx, row, own=False):
    rows = (
        await db.scalars(
            scoped(TripMilestone, ctx)
            .where(TripMilestone.trip_id == row.id)
            .order_by(TripMilestone.event_number)
        )
    ).all()
    return [
        (
            {
                key: getattr(item, key)
                for key in (
                    "id",
                    "event_number",
                    "milestone_type",
                    "occurred_at",
                    "recorded_at",
                    "source",
                )
            }
            if own
            else fields(item)
        )
        for item in rows
    ]


@router.get("/trips/{identifier}/milestones")
async def read_milestones(
    identifier: uuid.UUID, ctx: TenantContext = Depends(tenant), db: AsyncSession = Depends(get_db)
):
    ctx.require("trips.read")
    return await milestones(db, ctx, await find(db, ctx, Trip, identifier))


@router.get("/trips/{identifier}/assignments")
async def read_trip_assignments(
    identifier: uuid.UUID, ctx: TenantContext = Depends(tenant), db: AsyncSession = Depends(get_db)
):
    ctx.require("trips.read")
    await find(db, ctx, Trip, identifier)
    return [
        fields(row)
        for row in (
            await db.scalars(
                scoped(TripAssignment, ctx)
                .where(TripAssignment.trip_id == identifier)
                .order_by(TripAssignment.assigned_at, TripAssignment.id)
            )
        ).all()
    ]


@router.get("/driver/trips")
async def driver_trips(
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db),
    history: bool = False,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    ctx.require("driver_trip.read_own")
    driver = await own_profile(db, ctx)
    if driver is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    query = scoped(Trip, ctx).where(Trip.driver_id == driver.id)
    query = query.where(
        Trip.current_status.in_(TERMINAL) if history else Trip.current_status.not_in(TERMINAL)
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.scalars(
            query.order_by(Trip.scheduled_pickup_at, Trip.id).limit(limit).offset(offset)
        )
    ).all()
    return {
        "items": [await trip_view(db, ctx, row, True) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/driver/trips/{identifier}")
async def driver_trip(
    identifier: uuid.UUID, ctx: TenantContext = Depends(tenant), db: AsyncSession = Depends(get_db)
):
    return await trip_view(db, ctx, await own_trip(db, ctx, identifier), True)


@router.get("/driver/trips/{identifier}/milestones")
async def driver_milestones(
    identifier: uuid.UUID, ctx: TenantContext = Depends(tenant), db: AsyncSession = Depends(get_db)
):
    return await milestones(db, ctx, await own_trip(db, ctx, identifier), True)


@router.post("/driver/trips/{identifier}/transition")
async def driver_transition(
    identifier: uuid.UUID,
    payload: TripTransition,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db),
):
    return await transition(identifier, payload, ctx, db, True)
