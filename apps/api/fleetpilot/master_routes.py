"""Tenant-scoped master data; no operational trip states or public identity provisioning."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .audit import record
from .db import get_db
from .master_models import Customer, Driver, Vehicle
from .master_models import VehicleDriverAssignment as Assignment
from .master_schemas import (
    AssignmentInput,
    AssignmentOut,
    CustomerInput,
    CustomerOut,
    DriverInput,
    DriverOut,
    VehicleInput,
    VehicleOut,
)
from .models import Membership, Organization, User
from .permissions import resolve_permissions
from .tenancy import TenantContext, tenant

router = APIRouter(prefix="/api/v1", tags=["Fleet master data"])


def scoped(model, ctx):
    return select(model).where(model.organization_id == ctx.organization.id)


async def find(db, ctx, model, identifier):
    row = await db.scalar(scoped(model, ctx).where(model.id == identifier))
    if row is None:
        raise HTTPException(404, "Record not found.")
    return row


async def write_lock(db, ctx, permission):
    ctx.require(permission)
    # All master mutations and membership administration share this lock order.
    # Recheck access after waiting, so concurrent membership revocation cannot win a race.
    await db.execute(
        select(Organization.id).where(Organization.id == ctx.organization.id).with_for_update()
    )
    await db.refresh(ctx.membership)
    await db.refresh(ctx.organization)
    await db.refresh(ctx.user)
    if (
        not ctx.membership.active
        or ctx.organization.status != "ACTIVE"
        or not ctx.user.is_active
        or ctx.user.status != "ACTIVE"
        or permission
        not in resolve_permissions(ctx.membership.role, ctx.membership.permissions_json)
    ):
        raise HTTPException(403, "This action is no longer permitted.")


def search_pattern(search):
    return "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def require_current(ctx, permission):
    if permission not in resolve_permissions(ctx.membership.role, ctx.membership.permissions_json):
        raise HTTPException(403, "You do not have permission for this action.")


async def require_no_open_trips(db, ctx, model, identifier):
    from .trip_models import Trip

    column = (
        Trip.vehicle_id
        if model is Vehicle
        else Trip.customer_id
        if model is Customer
        else Trip.driver_id
    )
    if await db.scalar(
        scoped(Trip, ctx).where(
            column == identifier, Trip.current_status.not_in({"COMPLETED", "CANCELLED"})
        )
    ):
        raise HTTPException(409, "This resource has open trips. Close or reassign them first.")


async def validate_driver(db, ctx, payload, previous=None):
    if previous and payload.employment_status != "ACTIVE":
        await require_no_open_trips(db, ctx, Driver, previous.id)
    if payload.user_id != (previous.user_id if previous else None):
        require_current(ctx, "users.manage")
        if payload.user_id:
            linked = await db.scalar(
                select(Membership.id)
                .join(User, User.id == Membership.user_id)
                .where(
                    Membership.organization_id == ctx.organization.id,
                    Membership.user_id == payload.user_id,
                    Membership.active.is_(True),
                    Membership.role == "DRIVER",
                    User.is_active.is_(True),
                    User.status == "ACTIVE",
                )
            )
            if linked is None:
                raise HTTPException(422, "Link an active driver account in this organization.")
    if (
        previous
        and previous.operational_status == "ASSIGNED"
        and payload.employment_status != "ACTIVE"
    ):
        raise HTTPException(409, "Unassign this driver before changing employment status.")
    if previous and previous.employment_status == "INACTIVE":
        raise HTTPException(409, "Reactivate this driver before editing the profile.")


def resource_routes(
    domain, model, input_schema, output_schema, status_field, statuses, searchable, sortable
):
    singular = {"customers": "customer", "vehicles": "vehicle", "drivers": "driver"}[domain]

    async def listing(
        ctx: TenantContext = Depends(tenant),
        db: AsyncSession = Depends(get_db, scope="function"),
        search: str = Query("", max_length=160),
        status: str | None = None,
        sort: str = "created_at",
        direction: Literal["asc", "desc"] = "desc",
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1000000),
    ):
        ctx.require(f"{domain}.read")
        if sort not in sortable or (status is not None and status not in statuses):
            raise HTTPException(422, "Choose a supported sort field or status.")
        query = scoped(model, ctx)
        if status:
            query = query.where(getattr(model, status_field) == status)
        if search.strip():
            query = query.where(
                or_(
                    *(
                        getattr(model, field).ilike(search_pattern(search.strip()), escape="\\")
                        for field in searchable
                    )
                )
            )
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        column = getattr(model, sort)
        rows = (
            await db.scalars(
                query.order_by(column.asc() if direction == "asc" else column.desc(), model.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return {
            "items": [output_schema.model_validate(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def detail(
        identifier: uuid.UUID,
        ctx: TenantContext = Depends(tenant),
        db: AsyncSession = Depends(get_db, scope="function"),
    ):
        ctx.require(f"{domain}.read")
        return output_schema.model_validate(await find(db, ctx, model, identifier))

    async def create(
        payload: input_schema,
        ctx: TenantContext = Depends(tenant),
        db: AsyncSession = Depends(get_db, scope="function"),
    ):
        await write_lock(db, ctx, f"{domain}.create")
        if model is Driver:
            await validate_driver(db, ctx, payload)
        row = model(
            **payload.model_dump(),
            organization_id=ctx.organization.id,
            created_by=ctx.user.id,
            updated_by=ctx.user.id,
        )
        db.add(row)
        await db.flush()
        record(
            db,
            ctx,
            f"{singular}.created",
            singular,
            row.id,
            None,
            {"fields": sorted(payload.model_fields_set), status_field: getattr(row, status_field)},
        )
        await db.flush()
        return output_schema.model_validate(row)

    async def update(
        identifier: uuid.UUID,
        payload: input_schema,
        ctx: TenantContext = Depends(tenant),
        db: AsyncSession = Depends(get_db, scope="function"),
    ):
        await write_lock(db, ctx, f"{domain}.update")
        row = await find(db, ctx, model, identifier)
        if model is Driver:
            await validate_driver(db, ctx, payload, row)
        changes = {
            key: value for key, value in payload.model_dump().items() if getattr(row, key) != value
        }
        if changes:
            old_status = getattr(row, status_field)
            for key, value in changes.items():
                setattr(row, key, value)
            row.updated_by = ctx.user.id
            row.updated_at = datetime.now(timezone.utc)
            record(
                db,
                ctx,
                f"{singular}.updated",
                singular,
                row.id,
                {status_field: old_status},
                {"fields": sorted(changes), status_field: getattr(row, status_field)},
            )
            await db.flush()
        return output_schema.model_validate(row)

    async def change_state(identifier, active, ctx, db):
        await write_lock(db, ctx, f"{domain}.deactivate")
        row = await find(db, ctx, model, identifier)
        if not active:
            await require_no_open_trips(db, ctx, model, identifier)
        old = getattr(row, status_field)
        if model in (Vehicle, Driver):
            column = Assignment.vehicle_id if model is Vehicle else Assignment.driver_id
            if await db.scalar(
                scoped(Assignment, ctx).where(column == row.id, Assignment.is_current.is_(True))
            ):
                raise HTTPException(
                    409, "Unassign the current vehicle and driver before deactivating."
                )
        if (
            active
            and model is Vehicle
            and await db.scalar(
                text(
                    "SELECT id FROM maintenance_work_orders WHERE organization_id=:org AND vehicle_id=:id AND status='IN_PROGRESS' AND requires_vehicle_downtime LIMIT 1"
                ),
                {"org": ctx.organization.id, "id": row.id},
            )
        ):
            raise HTTPException(
                409, "Complete active downtime work before reactivating this vehicle."
            )
        target = ("AVAILABLE" if model is Vehicle else "ACTIVE") if active else "INACTIVE"
        if active and old != "INACTIVE":
            raise HTTPException(409, "Only inactive records can be reactivated.")
        if not active and old == "INACTIVE":
            raise HTTPException(409, "This record is already inactive.")
        setattr(row, status_field, target)
        if model is Driver:
            row.operational_status = "UNASSIGNED" if active else "INACTIVE"
        row.updated_by, row.updated_at = ctx.user.id, datetime.now(timezone.utc)
        record(
            db,
            ctx,
            f"{singular}.{'reactivated' if active else 'deactivated'}",
            singular,
            row.id,
            {status_field: old},
            {status_field: target},
        )
        await db.flush()
        return output_schema.model_validate(row)

    async def deactivate(
        identifier: uuid.UUID,
        ctx: TenantContext = Depends(tenant),
        db: AsyncSession = Depends(get_db, scope="function"),
    ):
        return await change_state(identifier, False, ctx, db)

    async def reactivate(
        identifier: uuid.UUID,
        ctx: TenantContext = Depends(tenant),
        db: AsyncSession = Depends(get_db, scope="function"),
    ):
        return await change_state(identifier, True, ctx, db)

    for suffix, method, handler, code in [
        ("", "GET", listing, 200),
        ("", "POST", create, 201),
        ("/{identifier}", "GET", detail, 200),
        ("/{identifier}", "PATCH", update, 200),
        ("/{identifier}/deactivate", "POST", deactivate, 200),
        ("/{identifier}/reactivate", "POST", reactivate, 200),
    ]:
        router.add_api_route(
            f"/{domain}{suffix}",
            handler,
            methods=[method],
            status_code=code,
            name=f"{domain}_{handler.__name__}",
        )


resource_routes(
    "customers",
    Customer,
    CustomerInput,
    CustomerOut,
    "status",
    {"ACTIVE", "INACTIVE"},
    ("company_name", "contact_person", "customer_code"),
    {"created_at", "updated_at", "company_name", "customer_code", "status"},
)
resource_routes(
    "vehicles",
    Vehicle,
    VehicleInput,
    VehicleOut,
    "status",
    {"AVAILABLE", "ASSIGNED", "MAINTENANCE", "INACTIVE"},
    ("unit_number", "plate_number", "make", "model"),
    {"created_at", "updated_at", "unit_number", "plate_number", "status", "registration_expiry"},
)
resource_routes(
    "drivers",
    Driver,
    DriverInput,
    DriverOut,
    "employment_status",
    {"ACTIVE", "ON_LEAVE", "SUSPENDED", "INACTIVE"},
    ("employee_number", "first_name", "last_name", "license_number"),
    {
        "created_at",
        "updated_at",
        "employee_number",
        "last_name",
        "employment_status",
        "license_expiry",
    },
)


async def assignment_view(db, ctx, row):
    vehicle = await find(db, ctx, Vehicle, row.vehicle_id)
    driver = await find(db, ctx, Driver, row.driver_id)
    return {
        **AssignmentOut.model_validate(row).model_dump(mode="json"),
        "unit_number": vehicle.unit_number,
        "driver_name": f"{driver.first_name} {driver.last_name}",
    }


@router.get("/vehicle-driver-assignments")
async def list_assignments(
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
    vehicle_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    is_current: bool | None = None,
    search: str = Query("", max_length=160),
    sort: Literal["assigned_at", "created_at"] = "assigned_at",
    direction: Literal["asc", "desc"] = "desc",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
):
    ctx.require("assignments.read")
    query = scoped(Assignment, ctx)
    if vehicle_id:
        await find(db, ctx, Vehicle, vehicle_id)
        query = query.where(Assignment.vehicle_id == vehicle_id)
    if driver_id:
        await find(db, ctx, Driver, driver_id)
        query = query.where(Assignment.driver_id == driver_id)
    if is_current is not None:
        query = query.where(Assignment.is_current == is_current)
    if search.strip():
        query = (
            query.join(Vehicle, Vehicle.id == Assignment.vehicle_id)
            .join(Driver, Driver.id == Assignment.driver_id)
            .where(
                Vehicle.organization_id == ctx.organization.id,
                Driver.organization_id == ctx.organization.id,
                or_(
                    Vehicle.unit_number.ilike(search_pattern(search.strip()), escape="\\"),
                    Driver.first_name.ilike(search_pattern(search.strip()), escape="\\"),
                    Driver.last_name.ilike(search_pattern(search.strip()), escape="\\"),
                ),
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    column = getattr(Assignment, sort)
    rows = (
        await db.scalars(
            query.order_by(column.asc() if direction == "asc" else column.desc(), Assignment.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {
        "items": [await assignment_view(db, ctx, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/vehicle-driver-assignments/{identifier}")
async def read_assignment(
    identifier: uuid.UUID, ctx: TenantContext = Depends(tenant), db: AsyncSession = Depends(get_db, scope="function")
):
    ctx.require("assignments.read")
    return await assignment_view(db, ctx, await find(db, ctx, Assignment, identifier))


@router.post("/vehicle-driver-assignments", status_code=201)
async def assign_driver(
    payload: AssignmentInput,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    await write_lock(db, ctx, "assignments.manage")
    require_current(ctx, "vehicles.assign_driver")
    vehicle = await find(db, ctx, Vehicle, payload.vehicle_id)
    driver = await find(db, ctx, Driver, payload.driver_id)
    if (
        vehicle.status != "AVAILABLE"
        or driver.employment_status != "ACTIVE"
        or driver.operational_status != "UNASSIGNED"
    ):
        raise HTTPException(409, "Choose an available vehicle and an active, unassigned driver.")
    row = Assignment(
        organization_id=ctx.organization.id, **payload.model_dump(), created_by=ctx.user.id
    )
    db.add(row)
    vehicle.status, driver.operational_status = "ASSIGNED", "ASSIGNED"
    for entity in (vehicle, driver):
        entity.updated_by, entity.updated_at = ctx.user.id, datetime.now(timezone.utc)
    await db.flush()
    record(
        db,
        ctx,
        "driver.assigned_to_vehicle",
        "assignment",
        row.id,
        None,
        {"vehicle_id": str(vehicle.id), "driver_id": str(driver.id)},
    )
    await db.flush()
    return await assignment_view(db, ctx, row)


@router.post("/vehicle-driver-assignments/{identifier}/unassign")
async def unassign_driver(
    identifier: uuid.UUID, ctx: TenantContext = Depends(tenant), db: AsyncSession = Depends(get_db, scope="function")
):
    await write_lock(db, ctx, "assignments.manage")
    require_current(ctx, "vehicles.assign_driver")
    row = await find(db, ctx, Assignment, identifier)
    if not row.is_current:
        raise HTTPException(409, "This assignment has already ended.")
    vehicle = await find(db, ctx, Vehicle, row.vehicle_id)
    driver = await find(db, ctx, Driver, row.driver_id)
    row.is_current, row.unassigned_at = False, datetime.now(timezone.utc)
    vehicle.status = "MAINTENANCE" if vehicle.status == "MAINTENANCE" else "AVAILABLE"
    driver.operational_status = "UNASSIGNED"
    for entity in (vehicle, driver):
        entity.updated_by, entity.updated_at = ctx.user.id, datetime.now(timezone.utc)
    record(
        db,
        ctx,
        "driver.unassigned_from_vehicle",
        "assignment",
        row.id,
        {"is_current": True},
        {"is_current": False, "vehicle_id": str(vehicle.id), "driver_id": str(driver.id)},
    )
    await db.flush()
    return await assignment_view(db, ctx, row)


@router.get("/driver-profile")
async def own_driver_profile(
    ctx: TenantContext = Depends(tenant), db: AsyncSession = Depends(get_db, scope="function")
):
    ctx.require("driver_app.view")
    profile = await db.scalar(scoped(Driver, ctx).where(Driver.user_id == ctx.user.id))
    if profile is None:
        return {"profile": None, "assignment": None}
    current = await db.scalar(
        scoped(Assignment, ctx).where(
            Assignment.driver_id == profile.id, Assignment.is_current.is_(True)
        )
    )
    assignment = None
    if current:
        vehicle = await find(db, ctx, Vehicle, current.vehicle_id)
        assignment = {
            "unit_number": vehicle.unit_number,
            "plate_number": vehicle.plate_number,
            "vehicle_type": vehicle.vehicle_type,
            "assigned_at": current.assigned_at,
        }
    return {
        "profile": {
            key: getattr(profile, key)
            for key in (
                "employee_number",
                "first_name",
                "last_name",
                "license_number",
                "license_type",
                "license_expiry",
                "employment_status",
            )
        },
        "assignment": assignment,
    }
