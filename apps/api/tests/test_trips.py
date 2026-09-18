import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context
from fleetpilot.trip_lifecycle import ACTIONS, FLOW

from .conftest import login
from .test_master_data import DATA, create, fleet

pytestmark = pytest.mark.asyncio


def body(rows, **extra):
    return {
        "customer_id": rows["customers"]["id"],
        "pickup_name": "Warehouse A",
        "pickup_address": "100 Test Road, Manila",
        "delivery_name": "Customer Site B",
        "delivery_address": "200 Test Road, Laguna",
        "scheduled_pickup_at": "2030-01-10T08:00:00+08:00",
        "scheduled_delivery_at": "2030-01-10T16:00:00+08:00",
        "special_instructions": "Use Gate 4",
        "dispatcher_notes": "Owner-only notes",
        **extra,
    }


async def create_trip(client, rows, assigned=True, **extra):
    assignment = (
        {"vehicle_id": rows["vehicles"]["id"], "driver_id": rows["drivers"]["id"]}
        if assigned
        else {}
    )
    response = await client.post("/api/v1/trips", json=body(rows, **assignment, **extra))
    assert response.status_code == 201, response.text
    return response.json()


async def act(client, trip, action, prefix="/api/v1/trips"):
    if action == "deliver":
        # Batch 5 deliberately replaces bare delivery with validated POD; preserve lifecycle assertions.
        from .delivery_helpers import submit_delivery

        return await submit_delivery(client, trip, review=prefix == "/api/v1/trips")
    response = await client.post(
        f"{prefix}/{trip['id']}/transition",
        json={"action": action, "expected_version": trip["version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def finish(client, trip, stop="deliver", prefix="/api/v1/trips"):
    for action in ACTIONS:
        trip = await act(client, trip, action, prefix)
        if action == stop:
            break
    return trip


async def test_owner_golden_workflow(client):
    await login(client)
    rows = await fleet(client)
    trip = await create_trip(client, rows, assigned=False)
    assert trip["trip_number"].startswith("TRIP-") and trip["current_status"] == "SCHEDULED"
    assigned = await client.post(
        f"/api/v1/trips/{trip['id']}/assign",
        json={
            "expected_version": trip["version"],
            "vehicle_id": rows["vehicles"]["id"],
            "driver_id": rows["drivers"]["id"],
        },
    )
    assert assigned.status_code == 200, assigned.text
    trip = assigned.json()
    assert (await client.get("/api/v1/dispatch?search=" + trip["trip_number"])).json()["total"] == 1
    trip = await finish(client, trip)
    assert trip["current_status"] == "DELIVERED" and trip["completed_at"] is None
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/complete",
        json={"expected_version": trip["version"], "closeout_reviewed": True},
    )
    assert response.status_code == 200, response.text
    trip = response.json()
    assert trip["current_status"] == "COMPLETED" and trip["completed_at"]
    reloaded = (await client.get(f"/api/v1/trips/{trip['id']}")).json()
    assert (
        reloaded["customer_name"] == "ACME Logistics Client"
        and reloaded["driver_name"] == "Juan Dela Cruz"
        and reloaded["vehicle_unit"] == "TRK-001"
    )
    events = (await client.get(f"/api/v1/trips/{trip['id']}/milestones")).json()
    assert [event["milestone_type"] for event in events] == ["TRIP_CREATED", *FLOW]
    assert [event["event_number"] for event in events] == list(range(1, len(events) + 1))
    assert all(
        event["occurred_at"]
        and event["recorded_at"]
        and event["recorded_by"]
        and event["source"] == "OWNER_WEB"
        for event in events
    )
    assert [e["occurred_at"] for e in events] == sorted(e["occurred_at"] for e in events)
    for path, payload in [
        ("", {**body(rows), "expected_version": trip["version"]}),
        ("/notes", {"dispatcher_notes": "tamper", "expected_version": trip["version"]}),
    ]:
        assert (
            await client.patch(f"/api/v1/trips/{trip['id']}{path}", json=payload)
        ).status_code == 409
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/cancel",
            json={"expected_version": trip["version"], "reason": "cannot undo"},
        )
    ).status_code == 409
    assert (await client.delete(f"/api/v1/trips/{trip['id']}")).status_code == 405
    logs = (await client.get(f"/api/v1/audit-logs?entity_type=trip&entity_id={trip['id']}")).json()
    assert {
        "trip.created",
        "trip.assigned",
        "trip.dispatched",
        "trip.transitioned",
        "trip.delivered",
        "trip.completed",
    } <= {log["action"] for log in logs}
    assert (await client.get("/api/v1/vehicle-driver-assignments")).json()["total"] == 0


async def test_create_assigned_update_and_filters(client):
    await login(client)
    rows = await fleet(client)
    trip = await create_trip(client, rows)
    changed = await client.patch(
        f"/api/v1/trips/{trip['id']}",
        json=body(rows, reference_number="PO-100", expected_version=trip["version"]),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["reference_number"] == "PO-100"
    for params in (
        {"search": "PO-100"},
        {"customer_id": rows["customers"]["id"]},
        {"vehicle_id": rows["vehicles"]["id"]},
        {"driver_id": rows["drivers"]["id"]},
        {"status": "SCHEDULED"},
        {"date_from": "2030-01-10", "date_to": "2030-01-10"},
        {"view": "upcoming"},
    ):
        result = (await client.get("/api/v1/trips", params=params)).json()
        assert result["total"] == 1
    assert (await client.get("/api/v1/trips?search=%25")).json()["total"] == 0
    assert (await client.get("/api/v1/trips?limit=1&offset=1")).json()["items"] == []
    assert (await client.get("/api/v1/trips?sort=DROP%20TABLE")).status_code == 422
    assert (
        await client.get("/api/v1/trips?date_from=2030-02-01&date_to=2030-01-01")
    ).status_code == 422
    other = await create_trip(client, rows, assigned=False)
    assert other["trip_number"] != trip["trip_number"]
    descending = (await client.get("/api/v1/trips?sort=trip_number&direction=desc&limit=1")).json()
    assert descending["items"][0]["id"] == other["id"]


@pytest.mark.parametrize(
    "stop,target",
    [
        (None, "deliver"),
        (None, "complete"),
        ("dispatch", "complete"),
        ("arrive_pickup", "complete"),
        ("cancel", "dispatch"),
        ("complete", "depart_pickup"),
    ],
)
async def test_explicit_invalid_transitions(client, stop, target):
    await login(client)
    rows = await fleet(client)
    trip = await create_trip(client, rows)
    if stop == "cancel":
        trip = (
            await client.post(
                f"/api/v1/trips/{trip['id']}/cancel",
                json={"expected_version": trip["version"], "reason": "Customer requested"},
            )
        ).json()
    elif stop:
        trip = await finish(client, trip, stop=stop if stop != "complete" else "deliver")
        if stop == "complete":
            trip = (
                await client.post(
                    f"/api/v1/trips/{trip['id']}/complete",
                    json={"expected_version": trip["version"], "closeout_reviewed": True},
                )
            ).json()
    endpoint = "complete" if target == "complete" else "transition"
    payload = {
        "expected_version": trip["version"],
        **({"closeout_reviewed": True} if target == "complete" else {"action": target}),
    }
    assert (
        await client.post(f"/api/v1/trips/{trip['id']}/{endpoint}", json=payload)
    ).status_code == 409


async def test_driver_own_visibility_actions_and_projection(client, admin_db):
    await login(client, "juan@example.com")
    identity = (await client.get("/api/v1/me")).json()
    await client.post("/api/v1/auth/logout")
    await login(client)
    rows = await fleet(client)
    response = await client.patch(
        f"/api/v1/drivers/{rows['drivers']['id']}",
        json={**DATA["drivers"], "user_id": identity["user"]["id"]},
    )
    assert response.status_code == 200
    trip = await create_trip(client, rows)
    unrelated = await create_trip(client, rows, assigned=False)
    trip = await act(client, trip, "dispatch")
    await client.post("/api/v1/auth/logout")
    await login(client, "juan@example.com")
    own = (await client.get("/api/v1/driver/trips")).json()
    assert own["total"] == 1 and own["items"][0]["id"] == trip["id"]
    assert own["items"][0]["next_action"] == "start_pickup"
    for key in (
        "dispatcher_notes",
        "organization_id",
        "created_by",
        "customer_reference",
        "driver_id",
    ):
        assert key not in own["items"][0]
    assert (await client.get(f"/api/v1/driver/trips/{unrelated['id']}")).status_code == 404
    assert (
        await client.get(f"/api/v1/driver/trips/{unrelated['id']}/milestones")
    ).status_code == 404
    assert (await client.get("/api/v1/trips")).status_code == 403
    assert (await client.get("/api/v1/dispatch")).status_code == 403
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/complete",
            json={"expected_version": trip["version"], "closeout_reviewed": True},
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/driver/trips/{trip['id']}/transition",
            json={"expected_version": trip["version"], "action": "deliver"},
        )
    ).status_code == 409
    for action in list(ACTIONS)[1:]:
        trip = await act(client, trip, action, prefix="/api/v1/driver/trips")
    events = (await client.get(f"/api/v1/driver/trips/{trip['id']}/milestones")).json()
    assert (
        events[-1]["source"] == "DRIVER_APP"
        and "notes" not in events[-1]
        and "recorded_by" not in events[-1]
    )
    # RLS itself also excludes unrelated same-tenant trips for this driver.
    async with Session() as db:
        await set_context(db, identity["user"]["id"], identity["organization"]["id"])
        assert await db.scalar(text("SELECT count(*) FROM trips")) == 1
        assert (
            await db.scalar(
                text("SELECT count(*) FROM trips WHERE id=:id"), {"id": unrelated["id"]}
            )
            == 0
        )
        await db.rollback()
    await client.post("/api/v1/auth/logout")
    await login(client)
    from .delivery_helpers import review_delivery

    trip = await review_delivery(client, trip)
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/complete",
        json={"expected_version": trip["version"], "closeout_reviewed": True},
    )
    assert response.status_code == 200
    trip = response.json()
    await client.post("/api/v1/auth/logout")
    await login(client, "juan@example.com")
    assert (await client.get("/api/v1/driver/trips")).json()["total"] == 0
    own = (await client.get("/api/v1/driver/trips?history=true")).json()
    assert own["items"][0]["next_action"] is None
    assert (
        await client.post(
            f"/api/v1/driver/trips/{trip['id']}/transition",
            json={"expected_version": trip["version"], "action": "depart_pickup"},
        )
    ).status_code == 409


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("OWNER", True),
        ("ADMIN", True),
        ("MANAGER", True),
        ("DISPATCHER", True),
        ("ACCOUNTING", False),
        ("MAINTENANCE", False),
        ("DRIVER", False),
    ],
)
async def test_trip_role_matrix(client, admin_db, role, allowed):
    await login(client)
    rows = await fleet(client)
    trip = await create_trip(client, rows)
    identity = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text("UPDATE organization_memberships SET role=:role WHERE id=:id"),
        {"role": role, "id": identity["membership"]["id"]},
    )
    await admin_db.commit()
    assert (await client.get("/api/v1/trips")).status_code == (200 if allowed else 403)
    assert (await client.get(f"/api/v1/trips/{trip['id']}/milestones")).status_code == (
        200 if allowed else 403
    )
    response = await client.post("/api/v1/trips", json=body(rows))
    assert response.status_code == (201 if allowed else 403)
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/transition",
        json={"expected_version": trip["version"], "action": "dispatch"},
    )
    assert response.status_code == (200 if allowed else 403)
    if allowed:
        trip = response.json()
        events = (await client.get(f"/api/v1/trips/{trip['id']}/milestones")).json()
        assert events[-1]["source"] == ("DISPATCHER_WEB" if role == "DISPATCHER" else "OWNER_WEB")
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/cancel",
            json={"expected_version": trip["version"], "reason": "Role test cancellation"},
        )
    ).status_code == (200 if allowed else 403)


@pytest.mark.parametrize("stop", [None, *list(ACTIONS)[:-1]])
async def test_cancellation_from_every_permitted_milestone(client, stop):
    await login(client)
    rows = await fleet(client)
    trip = await create_trip(client, rows)
    if stop:
        trip = await finish(client, trip, stop)
    path = f"/api/v1/trips/{trip['id']}"
    assert (
        await client.post(
            path + "/cancel", json={"expected_version": trip["version"], "reason": " "}
        )
    ).status_code == 422
    response = await client.post(
        path + "/cancel",
        json={"expected_version": trip["version"], "reason": "Customer postponed shipment"},
    )
    assert response.status_code == 200, response.text
    trip = response.json()
    assert trip["cancelled_at"] and trip["cancelled_by"] and trip["current_status"] == "CANCELLED"
    assert (
        await client.post(
            path + "/transition", json={"expected_version": trip["version"], "action": "dispatch"}
        )
    ).status_code == 409
    assert (
        await client.patch(
            path + "/notes",
            json={"expected_version": trip["version"], "dispatcher_notes": "tamper"},
        )
    ).status_code == 409
    assert (await client.get(path + "/milestones")).json()[-1]["milestone_type"] == "CANCELLED"
    assert (await client.get("/api/v1/trips?view=cancelled")).json()["total"] == 1
    assert (await client.get(path + "/assignments")).json()[0]["is_current"] is False


async def test_all_out_of_order_actions_and_stale_requests(client):
    await login(client)
    rows = await fleet(client)
    trip = await create_trip(client, rows)
    for correct in ACTIONS:
        count = len((await client.get(f"/api/v1/trips/{trip['id']}/milestones")).json())
        for invalid in ACTIONS:
            if invalid != correct:
                response = await client.post(
                    f"/api/v1/trips/{trip['id']}/transition",
                    json={"expected_version": trip["version"], "action": invalid},
                )
                assert response.status_code == 409
        assert len((await client.get(f"/api/v1/trips/{trip['id']}/milestones")).json()) == count
        old = trip
        trip = await act(client, trip, correct)
        assert (
            await client.post(
                f"/api/v1/trips/{trip['id']}/transition",
                json={"expected_version": old["version"], "action": correct},
            )
        ).status_code == 409
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/cancel",
            json={"expected_version": trip["version"], "reason": "Cannot reverse delivery"},
        )
    ).status_code == 409
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/complete",
            json={"expected_version": trip["version"], "closeout_reviewed": False},
        )
    ).status_code == 422


async def test_assignment_conflicts_and_concurrency(client):
    await login(client)
    rows = await fleet(client)
    trip = await create_trip(client, rows)
    assert (
        await client.post(
            "/api/v1/trips",
            json=body(rows, vehicle_id=rows["vehicles"]["id"], driver_id=rows["drivers"]["id"]),
        )
    ).status_code == 409
    later = await create_trip(
        client,
        rows,
        scheduled_pickup_at="2030-01-11T08:00:00+08:00",
        scheduled_delivery_at="2030-01-11T16:00:00+08:00",
    )
    responses = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/trips/{trip['id']}/transition",
                json={"expected_version": trip["version"], "action": "dispatch"},
            )
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    trip = next(r.json() for r in responses if r.status_code == 200)
    assert (
        await client.post(
            f"/api/v1/trips/{later['id']}/transition",
            json={"expected_version": later["version"], "action": "dispatch"},
        )
    ).status_code == 409
    for domain in ("vehicles", "drivers"):
        assert (
            await client.post(f"/api/v1/{domain}/{rows[domain]['id']}/deactivate")
        ).status_code == 409
    # Same fleet master assignment remains independent and unchanged.
    assignment = await client.post(
        "/api/v1/vehicle-driver-assignments",
        json={"vehicle_id": rows["vehicles"]["id"], "driver_id": rows["drivers"]["id"]},
    )
    assert assignment.status_code == 201
    assert (await client.get("/api/v1/vehicle-driver-assignments")).json()["total"] == 1
    trip = await act(client, trip, "start_pickup")
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/assign",
            json={
                "expected_version": trip["version"],
                "vehicle_id": rows["vehicles"]["id"],
                "driver_id": rows["drivers"]["id"],
            },
        )
    ).status_code == 409


async def test_reassignment_history_and_inactive_references(client):
    await login(client)
    rows = await fleet(client)
    vehicle = await create(
        client,
        "vehicles",
        {**DATA["vehicles"], "unit_number": "TRK-002", "plate_number": "XYZ-999"},
    )
    driver = await create(
        client, "drivers", {**DATA["drivers"], "employee_number": "DRV-002", "license_number": None}
    )
    trip = await create_trip(client, rows)
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/assign",
        json={
            "expected_version": trip["version"],
            "vehicle_id": vehicle["id"],
            "driver_id": driver["id"],
        },
    )
    assert response.status_code == 200, response.text
    history = (await client.get(f"/api/v1/trips/{trip['id']}/assignments")).json()
    assert len(history) == 2 and sum(item["is_current"] for item in history) == 1
    assert history[0]["ended_at"]
    logs = (await client.get(f"/api/v1/audit-logs?entity_type=trip&entity_id={trip['id']}")).json()
    assert "trip.reassigned" in [item["action"] for item in logs]
    for domain in ("vehicles", "drivers"):
        assert (
            await client.post(f"/api/v1/{domain}/{rows[domain]['id']}/deactivate")
        ).status_code == 200
    for refs in (
        {"vehicle_id": rows["vehicles"]["id"], "driver_id": driver["id"]},
        {"vehicle_id": vehicle["id"], "driver_id": rows["drivers"]["id"]},
    ):
        assert (await client.post("/api/v1/trips", json=body(rows, **refs))).status_code == 409


@pytest.mark.parametrize(
    "extra",
    [
        {"current_status": "COMPLETED"},
        {"trip_number": "INJECTED"},
        {"organization_id": str(uuid.uuid4())},
        {"created_by": str(uuid.uuid4())},
        {"scheduled_pickup_at": "2030-01-01T08:00:00"},
        {"scheduled_delivery_at": "2020-01-01T08:00:00Z"},
        {"pickup_latitude": 91},
        {"pickup_latitude": 14},
        {"cargo_weight": -1, "cargo_weight_unit": "kg"},
        {"cargo_weight": 10},
        {"driver_id": str(uuid.uuid4())},
    ],
)
async def test_trip_validation_and_mass_assignment(client, extra):
    await login(client)
    rows = await fleet(client)
    assert (await client.post("/api/v1/trips", json=body(rows, **extra))).status_code == 422


async def test_two_tenant_adversarial_and_direct_sql(client, admin_db):
    await login(client)
    rows_a = await fleet(client)
    trip_a = await create_trip(client, rows_a)
    await client.post("/api/v1/auth/logout")
    await login(client, "other-owner@example.com")
    b = (await client.get("/api/v1/me")).json()
    rows_b = await fleet(client)
    trip_b = await create_trip(client, rows_b)
    assert trip_a["trip_number"] == trip_b["trip_number"]
    # Search matching B's own number returns exactly B, never A.
    listing = (await client.get("/api/v1/trips", params={"search": trip_a["trip_number"]})).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == trip_b["id"]
    path = f"/api/v1/trips/{trip_a['id']}"
    for suffix in ("", "/milestones", "/assignments"):
        assert (await client.get(path + suffix)).status_code == 404
    assert (await client.patch(path, json=body(rows_b, expected_version=1))).status_code == 404
    for suffix, payload in [
        ("/assign", {"vehicle_id": rows_b["vehicles"]["id"], "driver_id": rows_b["drivers"]["id"]}),
        ("/transition", {"action": "dispatch"}),
        ("/cancel", {"reason": "Attack"}),
        ("/complete", {"closeout_reviewed": True}),
    ]:
        assert (
            await client.post(path + suffix, json={"expected_version": 1, **payload})
        ).status_code == 404
    for domain, field in [
        ("customers", "customer_id"),
        ("vehicles", "vehicle_id"),
        ("drivers", "driver_id"),
    ]:
        refs = {
            "vehicle_id": rows_b["vehicles"]["id"],
            "driver_id": rows_b["drivers"]["id"],
            field: rows_a[domain]["id"],
        }
        assert (await client.post("/api/v1/trips", json=body(rows_b, **refs))).status_code == 404
        assert (
            await client.get("/api/v1/trips", params={field: rows_a[domain]["id"]})
        ).status_code == 404
    tables = ("trips", "trip_milestones", "trip_assignments")
    flags = (
        await admin_db.execute(
            text(
                "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname=ANY(:tables)"
            ),
            {"tables": list(tables)},
        )
    ).all()
    assert len(flags) == 3 and all(row[1] and row[2] for row in flags)
    async with Session() as db:
        for table in tables:
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        await set_context(db, b["user"]["id"], b["organization"]["id"])
        assert await db.scalar(text("SELECT count(*) FROM trips")) == 1
        assert await db.scalar(text("SELECT count(*) FROM trip_milestones")) == 2
        for table in tables:
            column = "id" if table == "trips" else "trip_id"
            assert (
                await db.scalar(
                    text(f"SELECT count(*) FROM {table} WHERE {column}=:id"), {"id": trip_a["id"]}
                )
                == 0
            )
            assert (
                await db.execute(
                    text(f"DELETE FROM {table} WHERE {column}=:id"), {"id": trip_a["id"]}
                )
            ).rowcount == 0
        assert (
            await db.execute(
                text("UPDATE trips SET dispatcher_notes=:note WHERE id=:id"),
                {"note": "attack", "id": trip_a["id"]},
            )
        ).rowcount == 0
        await db.rollback()
    async with Session() as db:
        await set_context(db, b["user"]["id"], b["organization"]["id"])
        with pytest.raises(DBAPIError, match="fk_trip_customer_tenant"):
            await db.execute(
                text("UPDATE trips SET customer_id=:customer WHERE id=:id"),
                {"customer": rows_a["customers"]["id"], "id": trip_b["id"]},
            )
        await db.rollback()
    # The database guard also prevents a direct jump to delivered.
    async with Session() as db:
        await set_context(db, b["user"]["id"], b["organization"]["id"])
        with pytest.raises(DBAPIError, match="Delivery requires POD"):
            await db.execute(
                text(
                    "UPDATE trips SET current_status='DELIVERED',current_milestone='DELIVERED' WHERE id=:id"
                ),
                {"id": trip_b["id"]},
            )
        await db.rollback()
    # Migration owner bypasses RLS, but cannot silently edit immutable history.
    with pytest.raises(DBAPIError, match="immutable"):
        await admin_db.execute(
            text("UPDATE trip_milestones SET notes='tampered' WHERE trip_id=:id"),
            {"id": trip_a["id"]},
        )
    await admin_db.rollback()


async def test_completed_database_guard_and_transaction_rollback(client, admin_db):
    await login(client)
    rows = await fleet(client)
    trip = await finish(client, await create_trip(client, rows))
    trip = (
        await client.post(
            f"/api/v1/trips/{trip['id']}/complete",
            json={"expected_version": trip["version"], "closeout_reviewed": True},
        )
    ).json()
    for statement in (
        "UPDATE trips SET dispatcher_notes='tampered' WHERE id=:id",
        "DELETE FROM trips WHERE id=:id",
    ):
        with pytest.raises(DBAPIError, match="immutable|cannot be deleted"):
            await admin_db.execute(text(statement), {"id": trip["id"]})
        await admin_db.rollback()
    # Force an audit insert failure: the status, version and milestone must roll back together.
    other = await create_trip(client, rows)
    await admin_db.execute(
        text(
            "CREATE FUNCTION fail_trip_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='trip.dispatched' THEN RAISE EXCEPTION 'Test audit failure'; END IF; RETURN NEW; END $$"
        )
    )
    await admin_db.execute(
        text(
            "CREATE TRIGGER test_fail_trip_audit BEFORE INSERT ON audit_logs FOR EACH ROW EXECUTE FUNCTION fail_trip_audit()"
        )
    )
    await admin_db.commit()
    try:
        response = await client.post(
            f"/api/v1/trips/{other['id']}/transition",
            json={"expected_version": other["version"], "action": "dispatch"},
        )
        assert response.status_code == 500
        persisted = (await client.get(f"/api/v1/trips/{other['id']}")).json()
        assert (
            persisted["current_status"] == "SCHEDULED" and persisted["version"] == other["version"]
        )
        assert len((await client.get(f"/api/v1/trips/{other['id']}/milestones")).json()) == 2
    finally:
        await admin_db.execute(text("DROP TRIGGER test_fail_trip_audit ON audit_logs"))
        await admin_db.execute(text("DROP FUNCTION fail_trip_audit()"))
        await admin_db.commit()


async def test_cross_driver_and_tenant_driver_boundaries(client, admin_db):
    await login(client, "juan@example.com")
    juan = (await client.get("/api/v1/me")).json()
    await client.post("/api/v1/auth/logout")
    await login(client)
    rows = await fleet(client)
    await client.patch(
        f"/api/v1/drivers/{rows['drivers']['id']}",
        json={**DATA["drivers"], "user_id": juan["user"]["id"]},
    )
    own = await create_trip(client, rows)
    other_driver = await create(
        client,
        "drivers",
        {**DATA["drivers"], "employee_number": "DRV-OTHER", "license_number": None},
    )
    other_vehicle = await create(
        client,
        "vehicles",
        {**DATA["vehicles"], "unit_number": "TRK-OTHER", "plate_number": "ZZZ-111"},
    )
    unrelated = await create_trip(
        client, {**rows, "drivers": other_driver, "vehicles": other_vehicle}
    )
    await client.post("/api/v1/auth/logout")
    await login(client, "juan@example.com")
    listing = (await client.get("/api/v1/driver/trips")).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == own["id"]
    assert (await client.get(f"/api/v1/driver/trips/{unrelated['id']}")).status_code == 404
    assert (
        await client.post(
            f"/api/v1/driver/trips/{unrelated['id']}/transition",
            json={"expected_version": unrelated["version"], "action": "start_pickup"},
        )
    ).status_code == 404
    await client.post("/api/v1/auth/logout")
    await login(client, "other-owner@example.com")
    b = (await client.get("/api/v1/me")).json()
    rows_b = await fleet(client)
    trip_b = await create_trip(client, rows_b)
    await admin_db.execute(
        text("UPDATE organization_memberships SET role='DRIVER' WHERE id=:id"),
        {"id": b["membership"]["id"]},
    )
    await admin_db.execute(
        text("UPDATE drivers SET user_id=:user WHERE id=:id"),
        {"user": b["user"]["id"], "id": rows_b["drivers"]["id"]},
    )
    await admin_db.commit()
    assert (await client.get("/api/v1/driver/trips")).json()["items"][0]["id"] == trip_b["id"]
    for suffix in ("", "/milestones"):
        assert (await client.get(f"/api/v1/driver/trips/{own['id']}{suffix}")).status_code == 404
    async with Session() as db:
        await set_context(db, b["user"]["id"], b["organization"]["id"])
        assert await db.scalar(text("SELECT count(*) FROM trips")) == 1
        assert (
            await db.scalar(
                text("SELECT count(*) FROM trip_milestones WHERE trip_id=:id"), {"id": own["id"]}
            )
            == 0
        )
        await db.rollback()


async def test_denied_assignment_capability_and_missing_delivery_window(client, admin_db):
    await login(client)
    rows = await fleet(client)
    identity = (await client.get("/api/v1/me")).json()
    trip = await create_trip(client, rows, scheduled_delivery_at=None)
    response = await client.post(
        "/api/v1/trips",
        json=body(
            rows,
            vehicle_id=rows["vehicles"]["id"],
            driver_id=rows["drivers"]["id"],
            scheduled_pickup_at="2030-01-10T23:00:00+08:00",
            scheduled_delivery_at="2030-01-11T01:00:00+08:00",
        ),
    )
    assert response.status_code == 409
    assert (
        await client.post(f"/api/v1/customers/{rows['customers']['id']}/deactivate")
    ).status_code == 409
    await admin_db.execute(
        text(
            "UPDATE organization_memberships SET permissions_json=jsonb_build_object('deny',jsonb_build_array('dispatch.manage')) WHERE id=:id"
        ),
        {"id": identity["membership"]["id"]},
    )
    await admin_db.commit()
    assert (
        await client.post(
            "/api/v1/trips",
            json=body(rows, vehicle_id=rows["vehicles"]["id"], driver_id=rows["drivers"]["id"]),
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/transition",
            json={"expected_version": trip["version"], "action": "dispatch"},
        )
    ).status_code == 403
