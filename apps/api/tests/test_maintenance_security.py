import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context

from .conftest import login
from .delivery_helpers import image_bytes
from .test_expenses import cost, submit
from .test_maintenance import post, transition, work
from .test_master_data import DATA, assign, fleet
from .test_sync import setup

pytestmark = pytest.mark.asyncio


async def test_trip_costs_not_double_counted_and_active_trip_blocks_downtime(client):
    trip, _, data = await setup(client)
    r = await submit(client, trip, cost(amount="5000.00"))
    assert r.status_code == 200
    await login(client)
    w = await work(client, data["vehicles"]["id"], trip_id=trip["id"])
    await post(
        client,
        f"/maintenance/work-orders/{w['id']}/cost-items",
        dict(type="PART", description="Engine repair", unit_cost="12000"),
    )
    assert (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()[
        "submitted_total"
    ] == "5000.00"
    assert (await client.get(f"/api/v1/maintenance/work-orders/{w['id']}")).json()[
        "total_cost"
    ] == "12000.00"
    await post(
        client, f"/maintenance/work-orders/{w['id']}/start", dict(expected_version=1), expected=409
    )


@pytest.mark.parametrize("role", ["DRIVER", "DISPATCHER", "ACCOUNTING"])
async def test_unprivileged_work_denied(client, admin_db, role):
    await login(client)
    data = await fleet(client)
    who = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text("UPDATE organization_memberships SET role=:role WHERE user_id=:id"),
        dict(role=role, id=uuid.UUID(who["user"]["id"])),
    )
    await admin_db.commit()
    await post(
        client,
        "/maintenance/work-orders",
        dict(
            vehicle_id=data["vehicles"]["id"],
            type="REPAIR",
            title="Test work",
            description="Not authorized",
        ),
        expected=403,
    )


async def test_forced_rls_foreign_tenant_and_immutable_children(client, admin_db):
    await login(client)
    data = await fleet(client)
    w = await work(client, data["vehicles"]["id"])
    await post(
        client,
        f"/maintenance/work-orders/{w['id']}/cost-items",
        dict(type="PART", description="Part", unit_cost="12"),
    )
    who = (await client.get("/api/v1/me")).json()
    tables = [
        "maintenance_schedules",
        "maintenance_work_orders",
        "driver_defects",
        "maintenance_cost_items",
        "maintenance_evidence",
        "maintenance_events",
    ]
    for table in tables:
        assert await admin_db.scalar(
            text(
                "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname=:table"
            ),
            dict(table=table),
        )
    async with Session() as db:
        await set_context(db, who["user"]["id"], who["organization"]["id"])
        for table in tables:
            assert (await db.execute(text(f"DELETE FROM {table}"))).rowcount == 0
    with pytest.raises(DBAPIError):
        await admin_db.execute(text("UPDATE maintenance_cost_items SET total_cost=0"))
    await admin_db.rollback()
    await login(client, "other-owner@example.com")
    other = (await client.get("/api/v1/me")).json()
    async with Session() as db:
        await set_context(db, other["user"]["id"], other["organization"]["id"])
        for table in tables:
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0
    await post(
        client, f"/maintenance/work-orders/{w['id']}/start", dict(expected_version=1), expected=404
    )
    assert (await client.get("/api/v1/maintenance/work-orders?search=Oil")).json()["total"] == 0


async def test_cross_driver_private_defect_and_upload(client, admin_db):
    trip, _, data = await setup(client)
    payload = dict(
        vehicle_id=trip["vehicle_id"],
        trip_id=trip["id"],
        severity="SERIOUS",
        category="BRAKES",
        description="Soft brake pedal",
        reported_at_client=datetime.now(timezone.utc).isoformat(),
    )
    item = (await post(client, "/driver/defects", payload))["result"]["defect"]
    r = await client.post(
        f"/api/v1/defects/{item['id']}/evidence?filename=p.png",
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200
    evidence = r.json()["result"]["evidence_id"]
    await login(client)
    who = (await client.get("/api/v1/me")).json()
    # Link a second same-tenant driver account using the existing owner's synthetic identity.
    other = (
        await client.post(
            "/api/v1/drivers",
            json={
                **DATA["drivers"],
                "employee_number": "SECOND",
                "license_number": "SECOND",
                "user_id": None,
            },
        )
    ).json()
    assert other.get("id")
    await admin_db.execute(
        text("UPDATE drivers SET user_id=:actor WHERE id=:driver"),
        dict(actor=uuid.UUID(who["user"]["id"]), driver=uuid.UUID(other["id"])),
    )
    await admin_db.execute(
        text("UPDATE organization_memberships SET role='DRIVER' WHERE user_id=:id"),
        dict(id=uuid.UUID(who["user"]["id"])),
    )
    await admin_db.commit()
    assert (await client.get("/api/v1/defects/" + item["id"])).status_code == 404
    assert (await client.get("/api/v1/maintenance-evidence/" + evidence)).status_code == 404
    await post(client, "/driver/defects", payload, expected=404)
    r = await client.post(
        f"/api/v1/defects/{item['id']}/evidence?filename=p.png",
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 404


@pytest.mark.parametrize(
    "content,mime,name",
    [
        (b"", "image/png", "empty.png"),
        (b"MZ executable", "image/png", "fake.png"),
        (b"<svg/>", "image/svg+xml", "bad.svg"),
        (b"x" * 5242881, "image/png", "large.png"),
    ],
    ids=["empty", "spoofed", "svg", "oversized"],
)
async def test_invalid_files(client, content, mime, name):
    trip, _, _ = await setup(client)
    item = (
        await post(
            client,
            "/driver/defects",
            dict(
                vehicle_id=trip["vehicle_id"],
                trip_id=trip["id"],
                severity="MINOR",
                category="OTHER",
                description="Reported issue",
                reported_at_client=datetime.now(timezone.utc).isoformat(),
            ),
        )
    )["result"]["defect"]
    r = await client.post(
        f"/api/v1/defects/{item['id']}/evidence?filename={name}",
        content=content,
        headers={"Content-Type": mime, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code in (413, 422), r.text


async def test_master_unassign_cannot_clear_downtime_and_inactive_not_restored(client):
    await login(client)
    data = await fleet(client)
    assignment = (await assign(client, data)).json()
    vid = data["vehicles"]["id"]
    w = await transition(client, await work(client, vid), "start")
    assert (
        await client.post("/api/v1/vehicle-driver-assignments/" + assignment["id"] + "/unassign")
    ).status_code == 200
    assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] == "MAINTENANCE"
    assert (await client.post("/api/v1/vehicles/" + vid + "/deactivate")).status_code == 200
    assert (await client.post("/api/v1/vehicles/" + vid + "/reactivate")).status_code == 409
    await transition(
        client, w, "complete", odometer_at_completion="0", work_performed="Repair completed"
    )
    assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] == "INACTIVE"


async def test_schedule_attention_and_update_validation(client):
    await login(client)
    data = await fleet(client)
    vid = data["vehicles"]["id"]
    payload = dict(
        service_type="ENGINE_OIL",
        interval_type="DATE",
        date_interval_days=180,
        last_service_at="2020-01-01",
        warning_days=14,
    )
    s = await post(client, f"/vehicles/{vid}/maintenance-schedules", payload)
    assert (await client.get("/api/v1/maintenance/attention")).json()["total"] == 1
    assert (await client.get("/api/v1/maintenance/attention")).json()["items"][0][
        "status"
    ] == "OVERDUE"
    r = await client.put(
        "/api/v1/maintenance/schedules/" + s["id"], json={**payload, "is_active": False}
    )
    assert r.status_code == 200, r.text
    assert (await client.get("/api/v1/maintenance/attention")).json()["total"] == 0
    await post(
        client,
        f"/vehicles/{vid}/maintenance-schedules",
        {**payload, "next_due_at": "2040-01-01"},
        expected=422,
    )


async def test_audit_failure_rolls_back_work(client, admin_db, monkeypatch):
    await login(client)
    data = await fleet(client)
    import fleetpilot.maintenance_routes as routes

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic audit failure")

    monkeypatch.setattr(routes, "record", fail)
    response = await client.post(
        "/api/v1/maintenance/work-orders",
        json=dict(
            vehicle_id=data["vehicles"]["id"],
            type="REPAIR",
            title="Rollback test",
            description="Audit must be atomic",
        ),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 500
    assert (
        await admin_db.scalar(
            text("SELECT count(*) FROM driver_sync_commands WHERE command_type='maintenance_work'")
        )
        == 0
    )
    assert await admin_db.scalar(text("SELECT count(*) FROM maintenance_work_orders")) == 0


async def test_known_foreign_ids_reads_and_mutations(client, admin_db):
    trip, _, _ = await setup(client)
    defect = (
        await post(
            client,
            "/driver/defects",
            dict(
                vehicle_id=trip["vehicle_id"],
                trip_id=trip["id"],
                severity="MINOR",
                category="OTHER",
                description="Inspect vehicle",
                reported_at_client=datetime.now(timezone.utc).isoformat(),
            ),
        )
    )["result"]["defect"]
    await login(client)
    vid = trip["vehicle_id"]
    payload = dict(
        service_type="ENGINE_OIL",
        interval_type="ODOMETER",
        odometer_interval_km=5000,
        last_service_odometer="0",
        warning_km=1000,
    )
    schedule = await post(client, f"/vehicles/{vid}/maintenance-schedules", payload)
    w = await work(client, vid)
    response = await client.post(
        f"/api/v1/maintenance/work-orders/{w['id']}/evidence?filename=p.png&evidence_type=MAINTENANCE_RECEIPT",
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    evidence = response.json()["result"]["evidence_id"]
    await post(
        client,
        f"/maintenance/work-orders/{w['id']}/cost-items",
        dict(type="PART", description="Part", unit_cost="1"),
    )
    tables = [
        "maintenance_schedules",
        "maintenance_work_orders",
        "driver_defects",
        "maintenance_cost_items",
        "maintenance_evidence",
        "maintenance_events",
    ]
    for table in tables:
        assert await admin_db.scalar(text(f"SELECT count(*) FROM {table}")) > 0
    await login(client, "other-owner@example.com")
    other = (await client.get("/api/v1/me")).json()
    async with Session() as db:
        await set_context(db, other["user"]["id"], other["organization"]["id"])
        for table in tables:
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0
    for path in [
        f"/vehicles/{vid}/maintenance",
        f"/maintenance/work-orders/{w['id']}",
        f"/defects/{defect['id']}",
        f"/maintenance-evidence/{evidence}",
    ]:
        assert (await client.get("/api/v1" + path)).status_code == 404
    assert (
        await client.put("/api/v1/maintenance/schedules/" + schedule["id"], json=payload)
    ).status_code == 404
    await post(client, f"/vehicles/{vid}/maintenance-schedules", payload, expected=404)
    await post(
        client,
        f"/maintenance/work-orders/{w['id']}/cost-items",
        dict(type="PART", description="Part", unit_cost="1"),
        expected=404,
    )
    await post(
        client, f"/defects/{defect['id']}/review", dict(reason="Foreign review"), expected=404
    )
    response = await client.post(
        f"/api/v1/maintenance/work-orders/{w['id']}/evidence?filename=p.png&evidence_type=MAINTENANCE_RECEIPT",
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 404
    for domain in ["schedules", "work-orders", "defects", "attention"]:
        assert (await client.get("/api/v1/maintenance/" + domain)).json()["total"] == 0


async def test_concurrent_defect_and_photo_replay(client, admin_db):
    trip, _, _ = await setup(client)
    payload = dict(
        vehicle_id=trip["vehicle_id"],
        trip_id=trip["id"],
        severity="SERIOUS",
        category="BRAKES",
        description="Soft brake pedal",
        reported_at_client=datetime.now(timezone.utc).isoformat(),
    )
    key = str(uuid.uuid4())
    replies = await asyncio.gather(
        *(post(client, "/driver/defects", payload, key) for _ in range(2))
    )
    assert {r["outcome"] for r in replies} == {"APPLIED", "ALREADY_APPLIED"}
    identifier = replies[0]["result"]["defect"]["id"]
    photo_key = str(uuid.uuid4())
    replies = await asyncio.gather(
        *(
            client.post(
                f"/api/v1/defects/{identifier}/evidence?filename=p.png",
                content=image_bytes(),
                headers={"Content-Type": "image/png", "Idempotency-Key": photo_key},
            )
            for _ in range(2)
        )
    )
    assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
    assert {r.json()["outcome"] for r in replies} == {"APPLIED", "ALREADY_APPLIED"}
    assert await admin_db.scalar(text("SELECT count(*) FROM driver_defects")) == 1
    assert await admin_db.scalar(text("SELECT count(*) FROM maintenance_evidence")) == 1
    assert (
        await admin_db.scalar(
            text("SELECT count(*) FROM audit_logs WHERE action='defect.reported'")
        )
        == 1
    )


async def test_scheduled_dispatch_and_direct_status_bypass_denied(client, admin_db):
    from .test_trips import create_trip

    await login(client)
    data = await fleet(client)
    trip = await create_trip(client, data)
    vid = data["vehicles"]["id"]
    w = await transition(client, await work(client, vid), "start")
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/transition",
        json=dict(action="dispatch", expected_version=trip["version"]),
    )
    assert response.status_code == 409, response.text
    with pytest.raises(DBAPIError):
        await admin_db.execute(
            text("UPDATE vehicles SET status='AVAILABLE' WHERE id=:id"), dict(id=uuid.UUID(vid))
        )
    await admin_db.rollback()
    await transition(
        client, w, "complete", odometer_at_completion="0", work_performed="Service finished"
    )
    with pytest.raises(DBAPIError):
        await admin_db.execute(
            text("UPDATE maintenance_work_orders SET description='Tampered' WHERE id=:id"),
            dict(id=uuid.UUID(w["id"])),
        )
    await admin_db.rollback()


async def test_reviewed_fuel_and_combined_service_completion(client):
    from datetime import date, timedelta

    trip, _, _ = await setup(client)
    response = await submit(
        client, trip, cost("FUEL", amount=None, liters="10", price_per_liter="60", odometer="51000")
    )
    assert response.status_code == 200
    result = response.json()["result"]
    await login(client)
    vid = trip["vehicle_id"]
    assert (await client.get(f"/api/v1/vehicles/{vid}/maintenance")).json()[
        "trusted_odometer"
    ] == "0"
    response = await client.post(
        f"/api/v1/expenses/{result['expense']['id']}/review",
        json=dict(expected_version=result["trip_version"], notes="Reviewed reading"),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    assert (await client.get(f"/api/v1/vehicles/{vid}/maintenance")).json()[
        "trusted_odometer"
    ] == "51000.0"
    schedule = await post(
        client,
        f"/vehicles/{vid}/maintenance-schedules",
        dict(
            service_type="ENGINE_OIL",
            interval_type="ODOMETER_OR_DATE",
            odometer_interval_km=5000,
            date_interval_days=180,
            last_service_odometer="45000",
            last_service_at="2026-01-01",
            warning_km=1000,
            warning_days=14,
        ),
    )
    # Inspection does not require downtime and can coexist with an active trip.
    response = await post(
        client,
        "/maintenance/work-orders",
        dict(
            vehicle_id=vid,
            type="INSPECTION",
            title="Inspection",
            description="Check vehicle condition",
            maintenance_schedule_id=schedule["id"],
        ),
    )
    w = await transition(client, response["result"]["work_order"], "start")
    await post(
        client,
        f"/maintenance/work-orders/{w['id']}/complete",
        dict(
            expected_version=w["version"],
            odometer_at_completion="50000",
            work_performed="Inspected",
        ),
        expected=422,
    )
    w = await transition(
        client,
        w,
        "complete",
        odometer_at_completion="51250",
        work_performed="Inspected and serviced",
    )
    history = (await client.get(f"/api/v1/vehicles/{vid}/maintenance")).json()
    assert history["trusted_odometer"] == "51250.0"
    assert history["schedules"][0]["next_due_odometer"] == "56250.0"
    assert date.fromisoformat(history["schedules"][0]["next_due_at"]) == date.fromisoformat(
        w["completed_at"][:10]
    ) + timedelta(days=180)
    assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] != "MAINTENANCE"


async def test_evidence_read_restrictive_override(client, admin_db):
    trip, _, _ = await setup(client)
    item = (
        await post(
            client,
            "/driver/defects",
            dict(
                vehicle_id=trip["vehicle_id"],
                trip_id=trip["id"],
                severity="MINOR",
                category="OTHER",
                description="Issue reported",
                reported_at_client=datetime.now(timezone.utc).isoformat(),
            ),
        )
    )["result"]["defect"]
    response = await client.post(
        f"/api/v1/defects/{item['id']}/evidence?filename=p.png",
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    evidence = response.json()["result"]["evidence_id"]
    await login(client)
    who = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text(
            "UPDATE organization_memberships SET permissions_json=CAST(:deny AS jsonb) WHERE user_id=:id"
        ),
        dict(deny='{"deny":["maintenance.evidence.read"]}', id=uuid.UUID(who["user"]["id"])),
    )
    await admin_db.commit()
    assert (await client.get("/api/v1/maintenance-evidence/" + evidence)).status_code == 403
