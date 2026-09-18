"""Vehicle maintenance commands, private evidence and driver-owned defect reports."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from . import maintenance_models  # noqa: F401
from .audit import record
from .delivery_routes import Context, Database
from .evidence_storage import MAX_FILE_BYTES, storage, validate_image
from .expense_routes import rows, safe
from .maintenance_schemas import (
    CostInput,
    DefectInput,
    ReviewInput,
    ScheduleInput,
    WorkAction,
    WorkInput,
    next_due,
    schedule_state,
)
from .master_models import Vehicle
from .master_routes import find, write_lock
from .sync_routes import receipt
from .trip_routes import own_profile

router = APIRouter(prefix="/api/v1", tags=["Maintenance"])
STAFF = "maintenance.read"
TABLES = {
    "schedules": "maintenance_schedules",
    "work-orders": "maintenance_work_orders",
    "defects": "driver_defects",
}


async def sql(db, statement, **params):
    return await db.execute(text(statement), params)


async def one(db, ctx, table, identifier):
    found = await rows(
        db,
        f"SELECT * FROM {table} WHERE organization_id=:org AND id=:id",
        org=ctx.organization.id,
        id=identifier,
    )
    if not found:
        raise HTTPException(404, "Maintenance record not found.")
    return found[0]


async def trusted(db, ctx, vehicle):
    await find(db, ctx, Vehicle, vehicle)
    return await db.scalar(
        text(
            "SELECT greatest(coalesce(odometer,0),coalesce(reviewed_fuel_odometer,0),coalesce(maintenance_odometer,0)) FROM vehicles WHERE organization_id=:org AND id=:id"
        ),
        {"org": ctx.organization.id, "id": vehicle},
    )


async def event(db, ctx, action, vehicle, work=None, defect=None, schedule=None, notes=None):
    identifier = (
        (
            schedule
            if action.startswith("maintenance_schedule.")
            else defect
            if action.startswith("defect.")
            else work
        )
        or defect
        or schedule
        or vehicle
    )
    await sql(
        db,
        """INSERT INTO maintenance_events(id,organization_id,vehicle_id,work_order_id,defect_id,schedule_id,action,notes,actor_id)
    VALUES(:id,:org,:vehicle,:work,:defect,:schedule,:action,:notes,:actor)""",
        id=uuid.uuid4(),
        org=ctx.organization.id,
        vehicle=vehicle,
        work=work,
        defect=defect,
        schedule=schedule,
        action=action,
        notes=notes,
        actor=ctx.user.id,
    )
    record(
        db,
        ctx,
        action,
        "maintenance",
        identifier,
        None,
        {
            "vehicle_id": str(vehicle),
            "work_order_id": str(work) if work else None,
            "defect_id": str(defect) if defect else None,
            "schedule_id": str(schedule) if schedule else None,
            "notes": notes,
        },
    )


async def save_receipt(
    db, ctx, key, digest, result, command, driver=None, trip=None, captured=None
):
    await db.flush()
    await sql(
        db,
        """INSERT INTO driver_sync_commands(organization_id,actor_user_id,idempotency_key,driver_id,trip_id,command_type,request_hash,result,occurred_at_client,clock_suspect)
    VALUES(:org,:actor,:key,:driver,:trip,:command,:hash,CAST(:result AS jsonb),:captured,:suspect)""",
        org=ctx.organization.id,
        actor=ctx.user.id,
        key=key,
        driver=driver,
        trip=trip,
        command=command,
        hash=digest,
        result=json.dumps(safe(result)),
        captured=captured or datetime.now(timezone.utc),
        suspect=bool(
            captured and abs((datetime.now(timezone.utc) - captured).total_seconds()) > 86400
        ),
    )
    await db.commit()
    db.info.pop("uncommitted_evidence", None)
    return {"outcome": "APPLIED", "result": safe(result)}


async def defect_access(db, ctx, identifier, write=False):
    driver = ctx.membership.role == "DRIVER"
    ctx.require(
        "driver_defect.create_own"
        if driver and write
        else "driver_defect.read_own"
        if driver
        else "defects.read"
    )
    item = await one(db, ctx, "driver_defects", identifier)
    if driver:
        profile = await own_profile(db, ctx)
        if not profile or profile.id != item["driver_id"] or item["created_by"] != ctx.user.id:
            raise HTTPException(404, "Defect not found.")
    return item


async def vehicle_ownership(db, ctx, vehicle, trip=None):
    profile = await own_profile(db, ctx)
    if not profile or profile.employment_status != "ACTIVE":
        raise HTTPException(403, "Active linked driver required.")
    if trip:
        valid = await db.scalar(
            text(
                "SELECT id FROM trips WHERE organization_id=:org AND id=:trip AND vehicle_id=:vehicle AND driver_id=:driver AND current_status NOT IN ('COMPLETED','CANCELLED')"
            ),
            dict(org=ctx.organization.id, trip=trip, vehicle=vehicle, driver=profile.id),
        )
    else:
        valid = await db.scalar(
            text("""SELECT id FROM vehicle_driver_assignments WHERE organization_id=:org AND vehicle_id=:vehicle AND driver_id=:driver AND is_current
        UNION ALL SELECT id FROM trips WHERE organization_id=:org AND vehicle_id=:vehicle AND driver_id=:driver AND current_status NOT IN ('COMPLETED','CANCELLED') LIMIT 1"""),
            dict(org=ctx.organization.id, vehicle=vehicle, driver=profile.id),
        )
    if not valid:
        raise HTTPException(404, "Assigned vehicle not found.")
    return profile


@router.get("/vehicles/{vehicle_id}/maintenance")
async def vehicle_history(vehicle_id: uuid.UUID, ctx: Context, db: Database):
    ctx.require(STAFF)
    reading = await trusted(db, ctx, vehicle_id)
    today = (await db.scalar(text("SELECT current_timestamp"))).astimezone(timezone.utc).date()
    schedules = await rows(
        db,
        "SELECT * FROM maintenance_schedules WHERE organization_id=:org AND vehicle_id=:vehicle ORDER BY created_at,id",
        org=ctx.organization.id,
        vehicle=vehicle_id,
    )
    for item in schedules:
        item["due_status"] = schedule_state(item, reading, today)
    work = await rows(
        db,
        """SELECT w.*,coalesce((SELECT sum(c.total_cost) FROM maintenance_cost_items c WHERE c.organization_id=w.organization_id AND c.work_order_id=w.id),0) AS total_cost FROM maintenance_work_orders w WHERE w.organization_id=:org AND w.vehicle_id=:vehicle ORDER BY w.created_at DESC,w.id LIMIT 100""",
        org=ctx.organization.id,
        vehicle=vehicle_id,
    )
    defects = await rows(
        db,
        "SELECT * FROM driver_defects WHERE organization_id=:org AND vehicle_id=:vehicle ORDER BY created_at DESC,id LIMIT 100",
        org=ctx.organization.id,
        vehicle=vehicle_id,
    )
    return safe(
        dict(trusted_odometer=reading, schedules=schedules, work_orders=work, defects=defects)
    )


@router.post("/vehicles/{vehicle_id}/maintenance-schedules")
async def create_schedule(
    vehicle_id: uuid.UUID, payload: ScheduleInput, ctx: Context, db: Database
):
    await write_lock(db, ctx, "maintenance.schedule.create")
    await trusted(db, ctx, vehicle_id)
    identifier = uuid.uuid4()
    values = payload.model_dump()
    values.update(next_due(values))
    columns = ",".join(values)
    params = ",".join(":" + k for k in values)
    await sql(
        db,
        f"INSERT INTO maintenance_schedules(id,organization_id,vehicle_id,created_by,{columns}) VALUES(:id,:org,:vehicle,:actor,{params})",
        id=identifier,
        org=ctx.organization.id,
        vehicle=vehicle_id,
        actor=ctx.user.id,
        **values,
    )
    await event(db, ctx, "maintenance_schedule.created", vehicle_id, schedule=identifier)
    return safe(await one(db, ctx, "maintenance_schedules", identifier))


@router.put("/maintenance/schedules/{identifier}")
async def update_schedule(
    identifier: uuid.UUID, payload: ScheduleInput, ctx: Context, db: Database
):
    await write_lock(db, ctx, "maintenance.schedule.update")
    old = await one(db, ctx, "maintenance_schedules", identifier)
    if await db.scalar(
        text(
            "SELECT id FROM maintenance_work_orders WHERE organization_id=:org AND maintenance_schedule_id=:id AND status NOT IN ('COMPLETED','CANCELLED') LIMIT 1"
        ),
        dict(org=ctx.organization.id, id=identifier),
    ):
        raise HTTPException(409, "Close linked work orders before changing this schedule.")
    values = payload.model_dump()
    values.update(next_due(values))
    await sql(
        db,
        "UPDATE maintenance_schedules SET "
        + ",".join(k + "=:" + k for k in values)
        + ",updated_at=clock_timestamp() WHERE organization_id=:org AND id=:id",
        org=ctx.organization.id,
        id=identifier,
        **values,
    )
    await event(
        db,
        ctx,
        "maintenance_schedule.updated",
        old["vehicle_id"],
        schedule=identifier,
        notes="Schedule settings updated; prior service history retained.",
    )
    return safe(await one(db, ctx, "maintenance_schedules", identifier))


@router.get("/maintenance/attention")
async def attention(
    ctx: Context,
    db: Database,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=100),
    view: Literal["NEEDS_ATTENTION", "UPCOMING"] = "NEEDS_ATTENTION",
):
    ctx.require(STAFF)
    due = "(s.next_due_odometer IS NOT NULL AND greatest(coalesce(v.odometer,0),coalesce(v.reviewed_fuel_odometer,0),coalesce(v.maintenance_odometer,0)) >= s.next_due_odometer) OR (s.next_due_at IS NOT NULL AND (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date >= s.next_due_at)"
    warning = "(s.next_due_odometer IS NOT NULL AND greatest(coalesce(v.odometer,0),coalesce(v.reviewed_fuel_odometer,0),coalesce(v.maintenance_odometer,0)) >= s.next_due_odometer-s.warning_km) OR (s.next_due_at IS NOT NULL AND (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date >= s.next_due_at-s.warning_days)"
    condition = f"({due})" if view == "NEEDS_ATTENTION" else f"NOT ({due}) AND ({warning})"
    overdue = due.replace(" >= ", " > ")
    query = f"""SELECT s.id,s.vehicle_id,s.service_type AS title,'SCHEDULE' AS kind,s.created_at,CASE WHEN ({overdue}) THEN 'OVERDUE' WHEN ({due}) THEN 'DUE' ELSE 'UPCOMING' END AS status FROM maintenance_schedules s JOIN vehicles v ON v.organization_id=s.organization_id AND v.id=s.vehicle_id WHERE s.organization_id=:org AND s.is_active AND ({condition})"""
    if view == "NEEDS_ATTENTION":
        query += """ UNION ALL SELECT id,vehicle_id,title,'WORK_ORDER',created_at,status FROM maintenance_work_orders WHERE organization_id=:org AND priority IN ('HIGH','CRITICAL') AND status NOT IN ('COMPLETED','CANCELLED')
        UNION ALL SELECT id,vehicle_id,description,'DEFECT',created_at,status FROM driver_defects WHERE organization_id=:org AND severity='CRITICAL' AND status NOT IN ('RESOLVED','DISMISSED')"""
    filtered = "SELECT * FROM (" + query + ") q WHERE title ILIKE :search"
    params = dict(
        org=ctx.organization.id,
        search="%" + search.replace("%", r"\%").replace("_", r"\_") + "%",
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    items = await rows(
        db, filtered + " ORDER BY created_at DESC,id LIMIT :limit OFFSET :offset", **params
    )
    total = await db.scalar(text("SELECT count(*) FROM (" + filtered + ") n"), params)
    return safe(dict(items=items, total=total))


@router.get("/maintenance/{domain}")
async def listing(
    domain: Literal["schedules", "work-orders", "defects"],
    ctx: Context,
    db: Database,
    vehicle_id: uuid.UUID | None = None,
    status: str = Query("", max_length=30),
    search: str = Query("", max_length=100),
    view: Literal["ALL", "OPEN", "HISTORY"] = "ALL",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    ctx.require("defects.read" if domain == "defects" else STAFF)
    table = TABLES[domain]
    params = dict(
        org=ctx.organization.id,
        vehicle=vehicle_id,
        status=status,
        search="%" + search.replace("%", r"\%").replace("_", r"\_") + "%",
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    field = (
        "service_type"
        if domain == "schedules"
        else "title"
        if domain == "work-orders"
        else "description"
    )
    where = f"organization_id=:org AND (CAST(:vehicle AS uuid) IS NULL OR vehicle_id=:vehicle) AND {field} ILIKE :search"
    if domain == "work-orders" and view != "ALL":
        where += (
            " AND status "
            + ("IN" if view == "HISTORY" else "NOT IN")
            + " ('COMPLETED','CANCELLED')"
        )
    if domain != "schedules":
        where += " AND (:status='' OR status=:status)"
    items = await rows(
        db,
        f"SELECT * FROM {table} WHERE {where} ORDER BY created_at DESC,id LIMIT :limit OFFSET :offset",
        **params,
    )
    total = await db.scalar(text(f"SELECT count(*) FROM {table} WHERE {where}"), params)
    if domain == "schedules":
        today = datetime.now(timezone.utc).date()
        for item in items:
            item["due_status"] = schedule_state(
                item, await trusted(db, ctx, item["vehicle_id"]), today
            )
    return safe(dict(items=items, total=total, page=page, page_size=page_size))


@router.get("/maintenance/work-orders/{identifier}")
async def work_detail(identifier: uuid.UUID, ctx: Context, db: Database):
    ctx.require(STAFF)
    work = await one(db, ctx, "maintenance_work_orders", identifier)
    work["cost_items"] = await rows(
        db,
        "SELECT * FROM maintenance_cost_items WHERE organization_id=:org AND work_order_id=:id ORDER BY created_at,id",
        org=ctx.organization.id,
        id=identifier,
    )
    work["total_cost"] = sum((x["total_cost"] for x in work["cost_items"]), Decimal(0))
    work["events"] = await rows(
        db,
        "SELECT * FROM maintenance_events WHERE organization_id=:org AND work_order_id=:id ORDER BY created_at,id",
        org=ctx.organization.id,
        id=identifier,
    )
    work["evidence"] = await evidence_list(db, ctx, "work_order_id", identifier)
    return safe(work)


@router.post("/maintenance/work-orders")
async def create_work(
    payload: WorkInput, ctx: Context, db: Database, idempotency_key: uuid.UUID = Header()
):
    await write_lock(db, ctx, "maintenance.work_order.create")
    reading = await trusted(db, ctx, payload.vehicle_id)
    for table, identifier in [
        ("maintenance_schedules", payload.maintenance_schedule_id),
        ("driver_defects", payload.defect_report_id),
        ("trips", payload.trip_id),
    ]:
        if identifier:
            item = await one(db, ctx, table, identifier)
            if item["vehicle_id"] != payload.vehicle_id:
                raise HTTPException(404, "Source does not belong to this vehicle.")
            if table == "maintenance_schedules" and not item["is_active"]:
                raise HTTPException(
                    409, "Reactivate the maintenance schedule before creating work."
                )
    digest, replay = await receipt(
        db,
        ctx,
        idempotency_key,
        dict(command="maintenance_work", payload=payload.model_dump(mode="json")),
    )
    if replay:
        return replay
    if payload.defect_report_id:
        ctx.require("defects.create_work_order")
        defect = await one(db, ctx, "driver_defects", payload.defect_report_id)
        if defect["status"] != "REVIEWED":
            raise HTTPException(409, "Review the defect before creating work.")
    identifier = uuid.uuid4()
    count = await db.scalar(
        text("SELECT count(*) FROM maintenance_work_orders WHERE organization_id=:org"),
        dict(org=ctx.organization.id),
    )
    values = payload.model_dump()
    columns = ",".join(values)
    params = ",".join(":" + k for k in values)
    await sql(
        db,
        f"INSERT INTO maintenance_work_orders(id,organization_id,created_by,work_order_number,odometer_at_open,{columns}) VALUES(:id,:org,:actor,:number,:reading,{params})",
        id=identifier,
        org=ctx.organization.id,
        actor=ctx.user.id,
        number=f"WO-{count + 1:06d}",
        reading=reading,
        **values,
    )
    await event(db, ctx, "work_order.created", payload.vehicle_id, work=identifier)
    if payload.defect_report_id:
        await sql(
            db,
            "UPDATE driver_defects SET status='WORK_ORDER_CREATED' WHERE organization_id=:org AND id=:id",
            org=ctx.organization.id,
            id=payload.defect_report_id,
        )
        await event(
            db,
            ctx,
            "defect.work_order_created",
            payload.vehicle_id,
            work=identifier,
            defect=payload.defect_report_id,
        )
    return await save_receipt(
        db,
        ctx,
        idempotency_key,
        digest,
        {"work_order": await work_detail(identifier, ctx, db)},
        "maintenance_work",
    )


@router.post("/maintenance/work-orders/{identifier}/{action}")
async def work_action(
    identifier: uuid.UUID,
    action: Literal["schedule", "start", "complete", "cancel"],
    payload: WorkAction,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    await write_lock(
        db,
        ctx,
        "maintenance.work_order.complete"
        if action == "complete"
        else "maintenance.work_order.update",
    )
    work = await one(db, ctx, "maintenance_work_orders", identifier)
    digest, replay = await receipt(
        db,
        ctx,
        idempotency_key,
        dict(
            command="maintenance_action",
            id=str(identifier),
            action=action,
            payload=payload.model_dump(mode="json"),
        ),
    )
    if replay:
        return replay
    valid = {
        "schedule": {"OPEN"},
        "start": {"OPEN", "SCHEDULED"},
        "complete": {"IN_PROGRESS"},
        "cancel": {"OPEN", "SCHEDULED"},
    }
    if work["status"] not in valid[action] or payload.expected_version != work["version"]:
        raise HTTPException(409, "Invalid or stale work order transition.")
    stamp = await db.scalar(text("SELECT clock_timestamp()"))
    fields = {}
    if action == "schedule":
        if not payload.scheduled_at:
            raise HTTPException(422, "Scheduled time is required.")
        fields.update(status="SCHEDULED", scheduled_at=payload.scheduled_at)
    if action == "cancel":
        if not payload.reason or len(payload.reason.strip()) < 3:
            raise HTTPException(422, "Cancellation reason required.")
        fields.update(status="CANCELLED")
    if action == "start":
        if work["requires_vehicle_downtime"]:
            active = await db.scalar(
                text(
                    "SELECT id FROM trips WHERE organization_id=:org AND vehicle_id=:vehicle AND current_status NOT IN ('SCHEDULED','COMPLETED','CANCELLED') LIMIT 1"
                ),
                dict(org=ctx.organization.id, vehicle=work["vehicle_id"]),
            )
            if active:
                raise HTTPException(
                    409, "Close or reassign the active trip before starting vehicle downtime."
                )
            fields["downtime_started_at"] = stamp
        fields.update(status="IN_PROGRESS", started_at=stamp)
    if action == "complete":
        minimum = await trusted(db, ctx, work["vehicle_id"])
        if (
            payload.odometer_at_completion is None
            or payload.odometer_at_completion < minimum
            or not payload.work_performed
        ):
            raise HTTPException(422, f"Work performed and odometer at least {minimum} required.")
        fields.update(
            status="COMPLETED",
            completed_at=stamp,
            odometer_at_completion=payload.odometer_at_completion,
            work_performed=payload.work_performed,
        )
        if work["downtime_started_at"]:
            fields["downtime_ended_at"] = stamp
    await sql(
        db,
        "UPDATE maintenance_work_orders SET "
        + ",".join(k + "=:" + k for k in fields)
        + ",version=version+1,updated_at=clock_timestamp() WHERE organization_id=:org AND id=:id",
        org=ctx.organization.id,
        id=identifier,
        **fields,
    )
    vehicle = await find(db, ctx, Vehicle, work["vehicle_id"])
    if action == "start" and work["requires_vehicle_downtime"] and vehicle.status != "INACTIVE":
        vehicle.status = "MAINTENANCE"
    if action == "complete":
        await sql(
            db,
            "UPDATE vehicles SET maintenance_odometer=greatest(coalesce(maintenance_odometer,0),:reading) WHERE organization_id=:org AND id=:id",
            org=ctx.organization.id,
            id=vehicle.id,
            reading=payload.odometer_at_completion,
        )
        if work["maintenance_schedule_id"]:
            schedule = await one(db, ctx, "maintenance_schedules", work["maintenance_schedule_id"])
            baseline = dict(
                last_service_odometer=payload.odometer_at_completion
                if schedule["odometer_interval_km"]
                else None,
                last_service_at=stamp.date() if schedule["date_interval_days"] else None,
            )
            due = next_due({**schedule, **baseline})
            await sql(
                db,
                "UPDATE maintenance_schedules SET last_service_odometer=:last_service_odometer,last_service_at=:last_service_at,next_due_odometer=:next_due_odometer,next_due_at=:next_due_at,updated_at=clock_timestamp() WHERE organization_id=:org AND id=:id",
                org=ctx.organization.id,
                id=schedule["id"],
                **baseline,
                **due,
            )
            await event(
                db,
                ctx,
                "maintenance_schedule.updated",
                vehicle.id,
                work=identifier,
                schedule=schedule["id"],
                notes="Next service recalculated from completed maintenance.",
            )
        if work["defect_report_id"]:
            await sql(
                db,
                "UPDATE driver_defects SET status='RESOLVED' WHERE organization_id=:org AND id=:id",
                org=ctx.organization.id,
                id=work["defect_report_id"],
            )
            await event(
                db,
                ctx,
                "defect.resolved",
                vehicle.id,
                work=identifier,
                defect=work["defect_report_id"],
                notes=payload.work_performed,
            )
        blocking = await db.scalar(
            text(
                "SELECT id FROM maintenance_work_orders WHERE organization_id=:org AND vehicle_id=:id AND status='IN_PROGRESS' AND requires_vehicle_downtime LIMIT 1"
            ),
            dict(org=ctx.organization.id, id=vehicle.id),
        )
        if not blocking and vehicle.status == "MAINTENANCE":
            assigned = await db.scalar(
                text(
                    "SELECT id FROM vehicle_driver_assignments WHERE organization_id=:org AND vehicle_id=:id AND is_current"
                ),
                dict(org=ctx.organization.id, id=vehicle.id),
            )
            vehicle.status = "ASSIGNED" if assigned else "AVAILABLE"
    await db.flush()
    await event(
        db,
        ctx,
        "work_order."
        + {
            "schedule": "scheduled",
            "start": "started",
            "complete": "completed",
            "cancel": "cancelled",
        }[action],
        vehicle.id,
        work=identifier,
        notes=payload.reason or payload.work_performed,
    )
    return await save_receipt(
        db,
        ctx,
        idempotency_key,
        digest,
        {"work_order": await work_detail(identifier, ctx, db)},
        "maintenance_action",
    )


@router.post("/maintenance/work-orders/{identifier}/cost-items")
async def create_cost(
    identifier: uuid.UUID,
    payload: CostInput,
    ctx: Context,
    db: Database,
    idempotency_key: uuid.UUID = Header(),
):
    await write_lock(db, ctx, "maintenance.cost.manage")
    work = await one(db, ctx, "maintenance_work_orders", identifier)
    digest, replay = await receipt(
        db,
        ctx,
        idempotency_key,
        dict(
            command="maintenance_cost", id=str(identifier), payload=payload.model_dump(mode="json")
        ),
    )
    if replay:
        return replay
    if work["status"] in ("COMPLETED", "CANCELLED"):
        raise HTTPException(409, "Closed maintenance costs are immutable.")
    values = payload.model_dump()
    values["total_cost"] = payload.total
    item = uuid.uuid4()
    await sql(
        db,
        "INSERT INTO maintenance_cost_items(id,organization_id,work_order_id,created_by,"
        + ",".join(values)
        + ") VALUES(:id,:org,:work,:actor,"
        + ",".join(":" + k for k in values)
        + ")",
        id=item,
        org=ctx.organization.id,
        work=identifier,
        actor=ctx.user.id,
        **values,
    )
    await event(
        db,
        ctx,
        "maintenance_cost.created",
        work["vehicle_id"],
        work=identifier,
        notes=f"{payload.type}: PHP {payload.total}",
    )
    return await save_receipt(
        db,
        ctx,
        idempotency_key,
        digest,
        {"cost_item": await one(db, ctx, "maintenance_cost_items", item)},
        "maintenance_cost",
    )


@router.get("/driver/maintenance-vehicles")
async def own_vehicles(ctx: Context, db: Database):
    ctx.require("driver_defect.create_own")
    profile = await own_profile(db, ctx)
    if not profile:
        return {"items": []}
    items = await rows(
        db,
        """SELECT v.id,v.unit_number,v.plate_number FROM vehicles v WHERE v.organization_id=:org AND
    (EXISTS(SELECT 1 FROM vehicle_driver_assignments a WHERE a.organization_id=v.organization_id AND a.vehicle_id=v.id AND a.driver_id=:driver AND a.is_current)
    OR EXISTS(SELECT 1 FROM trips t WHERE t.organization_id=v.organization_id AND t.vehicle_id=v.id AND t.driver_id=:driver AND t.current_status NOT IN ('COMPLETED','CANCELLED'))) ORDER BY v.unit_number""",
        org=ctx.organization.id,
        driver=profile.id,
    )
    return safe({"items": items})


@router.post("/driver/defects")
async def create_defect(
    payload: DefectInput, ctx: Context, db: Database, idempotency_key: uuid.UUID = Header()
):
    if ctx.membership.role != "DRIVER":
        raise HTTPException(403, "Driver account required.")
    await write_lock(db, ctx, "driver_defect.create_own")
    profile = await vehicle_ownership(db, ctx, payload.vehicle_id, payload.trip_id)
    digest, replay = await receipt(
        db, ctx, idempotency_key, dict(command="defect", payload=payload.model_dump(mode="json"))
    )
    if replay:
        return replay
    identifier = uuid.uuid4()
    values = payload.model_dump()
    await sql(
        db,
        "INSERT INTO driver_defects(id,organization_id,driver_id,created_by,"
        + ",".join(values)
        + ") VALUES(:id,:org,:driver,:actor,"
        + ",".join(":" + k for k in values)
        + ")",
        id=identifier,
        org=ctx.organization.id,
        driver=profile.id,
        actor=ctx.user.id,
        **values,
    )
    await event(db, ctx, "defect.reported", payload.vehicle_id, defect=identifier)
    return await save_receipt(
        db,
        ctx,
        idempotency_key,
        digest,
        {"defect": await one(db, ctx, "driver_defects", identifier)},
        "defect",
        profile.id,
        payload.trip_id,
        payload.reported_at_client,
    )


@router.get("/driver/defects")
async def own_defects(ctx: Context, db: Database, page: int = Query(1, ge=1)):
    ctx.require("driver_defect.read_own")
    if ctx.membership.role != "DRIVER":
        raise HTTPException(403, "Driver account required.")
    items = await rows(
        db,
        "SELECT * FROM driver_defects WHERE organization_id=:org AND created_by=:actor ORDER BY created_at DESC,id LIMIT 20 OFFSET :offset",
        org=ctx.organization.id,
        actor=ctx.user.id,
        offset=(page - 1) * 20,
    )
    return safe({"items": items})


@router.get("/defects/{identifier}")
async def defect_detail(identifier: uuid.UUID, ctx: Context, db: Database):
    item = await defect_access(db, ctx, identifier)
    item["evidence"] = await evidence_list(db, ctx, "defect_id", identifier)
    item["events"] = await rows(
        db,
        "SELECT * FROM maintenance_events WHERE organization_id=:org AND defect_id=:id ORDER BY created_at,id",
        org=ctx.organization.id,
        id=identifier,
    )
    return safe(item)


@router.post("/defects/{identifier}/{action}")
async def review_defect(
    identifier: uuid.UUID,
    action: Literal["review", "dismiss"],
    payload: ReviewInput,
    ctx: Context,
    db: Database,
):
    await write_lock(db, ctx, "defects.review")
    item = await one(db, ctx, "driver_defects", identifier)
    if item["status"] not in ("REPORTED", "REVIEWED") or (
        action == "review" and item["status"] != "REPORTED"
    ):
        raise HTTPException(409, "Defect cannot transition from its current state.")
    await sql(
        db,
        "UPDATE driver_defects SET status=:status WHERE organization_id=:org AND id=:id",
        status="REVIEWED" if action == "review" else "DISMISSED",
        org=ctx.organization.id,
        id=identifier,
    )
    await event(
        db,
        ctx,
        "defect." + ("reviewed" if action == "review" else "dismissed"),
        item["vehicle_id"],
        defect=identifier,
        notes=payload.reason,
    )
    return await defect_detail(identifier, ctx, db)


async def evidence_list(db, ctx, column, identifier):
    return await rows(
        db,
        f"SELECT id,evidence_type,original_filename,content_type,file_size,checksum,status,uploaded_by,uploaded_at FROM maintenance_evidence WHERE organization_id=:org AND {column}=:id ORDER BY uploaded_at,id",
        org=ctx.organization.id,
        id=identifier,
    )


# These routes precede the generic work-order action route after registration sorting below.
@router.post("/maintenance/work-orders/{identifier}/evidence")
@router.post("/defects/{identifier}/evidence")
async def upload(
    identifier: uuid.UUID,
    request: Request,
    ctx: Context,
    db: Database,
    filename: str = Query(min_length=1, max_length=160),
    evidence_type: Literal[
        "MAINTENANCE_RECEIPT",
        "SERVICE_INVOICE",
        "DEFECT_PHOTO",
        "MAINTENANCE_BEFORE_PHOTO",
        "MAINTENANCE_AFTER_PHOTO",
    ] = "DEFECT_PHOTO",
    idempotency_key: uuid.UUID = Header(),
):
    defect = request.url.path.startswith("/api/v1/defects/")
    permission = (
        "driver_defect.create_own"
        if defect and ctx.membership.role == "DRIVER"
        else "maintenance.evidence.upload"
    )
    await write_lock(db, ctx, permission)
    item = (
        await defect_access(db, ctx, identifier, True)
        if defect
        else await one(db, ctx, "maintenance_work_orders", identifier)
    )
    if defect and evidence_type != "DEFECT_PHOTO":
        raise HTTPException(422, "Defects accept defect photos only.")
    if defect and ctx.membership.role == "DRIVER":
        await vehicle_ownership(db, ctx, item["vehicle_id"], item["trip_id"])
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(413, "Image exceeds 5 MiB.")
    doc = dict(
        command="maintenance_evidence",
        id=str(identifier),
        defect=defect,
        filename=filename,
        type=evidence_type,
        mime=request.headers.get("content-type", ""),
        checksum=hashlib.sha256(data).hexdigest(),
    )
    digest, replay = await receipt(db, ctx, idempotency_key, doc)
    if replay:
        return replay
    if (
        item["status"] not in ("REPORTED", "REVIEWED")
        if defect
        else item["status"] in ("COMPLETED", "CANCELLED")
    ):
        raise HTTPException(409, "Evidence is closed for this record.")
    column = "defect_id" if defect else "work_order_id"
    if len(await evidence_list(db, ctx, column, identifier)) >= 12:
        raise HTTPException(409, "12-file history limit reached.")
    normalized, checksum = await run_in_threadpool(
        validate_image, bytes(data), filename, doc["mime"]
    )
    evidence_id = uuid.uuid4()
    key = f"{ctx.organization.id.hex}/{evidence_id.hex}.png"
    store = storage()
    db.info.setdefault("uncommitted_evidence", []).append((store, key))
    await run_in_threadpool(store.put, key, normalized)
    await sql(
        db,
        f"INSERT INTO maintenance_evidence(id,organization_id,{column},evidence_type,storage_key,original_filename,file_size,checksum,uploaded_by) VALUES(:id,:org,:parent,:type,:key,:filename,:size,:checksum,:actor)",
        id=evidence_id,
        org=ctx.organization.id,
        parent=identifier,
        type=evidence_type,
        key=key,
        filename=filename,
        size=len(normalized),
        checksum=checksum,
        actor=ctx.user.id,
    )
    await event(
        db,
        ctx,
        "maintenance_evidence.uploaded",
        item["vehicle_id"],
        defect=identifier if defect else None,
        work=None if defect else identifier,
    )
    return await save_receipt(
        db,
        ctx,
        idempotency_key,
        digest,
        {"evidence_id": str(evidence_id)},
        "maintenance_evidence",
        item.get("driver_id"),
        item.get("trip_id"),
    )


@router.get("/maintenance-evidence/{identifier}")
async def retrieve(identifier: uuid.UUID, ctx: Context, db: Database):
    item = await one(db, ctx, "maintenance_evidence", identifier)
    if ctx.membership.role != "DRIVER":
        ctx.require("maintenance.evidence.read")
    if item["defect_id"]:
        await defect_access(db, ctx, item["defect_id"])
    else:
        ctx.require("maintenance.evidence.read")
    try:
        data = await run_in_threadpool(storage().read, item["storage_key"])
    except FileNotFoundError as exc:
        raise HTTPException(404, "Evidence unavailable.") from exc
    if hashlib.sha256(data).hexdigest() != item["checksum"]:
        raise HTTPException(503, "Evidence integrity check failed.")
    return Response(
        data,
        media_type="image/png",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'inline; filename="maintenance.png"',
            "X-Content-Type-Options": "nosniff",
        },
    )


router.routes.sort(key=lambda route: ("{action}" in route.path, route.path.count("{")))
