"""Synthetic maintenance dataset for the existing LOCAL HTTPS/private-S3 restore drill."""

import hashlib
import uuid
from datetime import datetime, timezone

from .conftest import login
from .delivery_helpers import image_bytes
from .test_maintenance import post, transition, work
from .test_master_data import assign
from .test_trips import body


async def create(client, rows, trip):
    # Preserve Batch 11 safety: the operational trip is closed before downtime.
    assert (await client.get("/api/v1/trips/" + trip["id"])).json()["current_status"] == "COMPLETED"
    assert (await assign(client, rows)).status_code == 201
    await login(client, "juan@example.com")
    payload = dict(
        vehicle_id=rows["vehicles"]["id"],
        severity="SERIOUS",
        category="BRAKES",
        description="Brake pedal feels softer than normal.",
        reported_at_client=datetime.now(timezone.utc).isoformat(),
    )
    key = str(uuid.uuid4())
    defect = (await post(client, "/driver/defects", payload, key))["result"]["defect"]
    response = await client.post(
        f"/api/v1/defects/{defect['id']}/evidence?filename=defect.png",
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    evidence = (await client.get("/api/v1/defects/" + defect["id"])).json()["evidence"]
    await login(client)
    schedule = await post(
        client,
        f"/vehicles/{rows['vehicles']['id']}/maintenance-schedules",
        dict(
            service_type="ENGINE_OIL",
            interval_type="ODOMETER",
            odometer_interval_km=5000,
            last_service_odometer="45000",
            warning_km=1000,
        ),
    )
    await post(
        client, f"/defects/{defect['id']}/review", dict(reason="Inspect brakes and service vehicle")
    )
    order = await work(
        client,
        rows["vehicles"]["id"],
        defect_report_id=defect["id"],
        maintenance_schedule_id=schedule["id"],
        trip_id=trip["id"],
    )
    order = await transition(client, order, "start")
    response = await client.post(
        "/api/v1/trips",
        json=body(rows, vehicle_id=rows["vehicles"]["id"], driver_id=rows["drivers"]["id"]),
    )
    assert response.status_code == 409, response.text
    for kind, amount in [("PART", "11500.00"), ("LABOR", "500.00")]:
        await post(
            client,
            f"/maintenance/work-orders/{order['id']}/cost-items",
            dict(type=kind, description="Recovery service " + kind, unit_cost=amount),
        )
    response = await client.post(
        f"/api/v1/maintenance/work-orders/{order['id']}/evidence?filename=maintenance.png&evidence_type=MAINTENANCE_RECEIPT",
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    order = await transition(
        client,
        order,
        "complete",
        odometer_at_completion="50250",
        work_performed="Brakes repaired and oil serviced",
    )
    evidence += order["evidence"]
    return dict(
        work=order["id"],
        defect=defect["id"],
        schedule=schedule["id"],
        evidence=evidence,
        defect_key=key,
        defect_payload=payload,
    )


async def verify(client, state):
    item = state["maintenance"]
    await login(client)
    order = (await client.get("/api/v1/maintenance/work-orders/" + item["work"])).json()
    assert order["status"] == "COMPLETED" and order["total_cost"] == "12000.00"
    assert (
        len(order["cost_items"]) == 2
        and order["downtime_started_at"]
        and order["downtime_ended_at"]
    )
    defect = (await client.get("/api/v1/defects/" + item["defect"])).json()
    assert (
        defect["status"] == "RESOLVED"
        and defect["description"] == "Brake pedal feels softer than normal."
    )
    history = (await client.get(f"/api/v1/vehicles/{state['vehicle']}/maintenance")).json()
    assert history["schedules"][0]["id"] == item["schedule"]
    assert history["schedules"][0]["next_due_odometer"] == "55250.0"
    assert (await client.get(f"/api/v1/vehicles/{state['vehicle']}")).json()["status"] == "ASSIGNED"
    assert (await client.get(f"/api/v1/trips/{state['trip']}/expenses")).json()[
        "submitted_total"
    ] == "3450.00"
    for evidence in item["evidence"]:
        response = await client.get("/api/v1/maintenance-evidence/" + evidence["id"])
        assert (
            response.status_code == 200
            and hashlib.sha256(response.content).hexdigest() == evidence["checksum"]
        )
    await login(client, "juan@example.com")
    assert (await client.get("/api/v1/defects/" + item["defect"])).json()["status"] == "RESOLVED"
    replay = await post(client, "/driver/defects", item["defect_payload"], item["defect_key"])
    assert (
        replay["outcome"] == "ALREADY_APPLIED"
        and replay["result"]["defect"]["id"] == item["defect"]
    )
    assert (
        await client.get("/api/v1/maintenance-evidence/" + defect["evidence"][0]["id"])
    ).status_code == 200
    assert (await client.get("/api/v1/maintenance/work-orders/" + item["work"])).status_code == 403
    await client.post("/api/v1/auth/logout")
    for evidence in item["evidence"]:
        assert (
            await client.get("/api/v1/maintenance-evidence/" + evidence["id"])
        ).status_code == 401
    await login(client, "other-owner@example.com")
    for path in [
        "/maintenance/work-orders/" + item["work"],
        "/defects/" + item["defect"],
        f"/vehicles/{state['vehicle']}/maintenance",
    ]:
        assert (await client.get("/api/v1" + path)).status_code == 404
    for evidence in item["evidence"]:
        assert (
            await client.get("/api/v1/maintenance-evidence/" + evidence["id"])
        ).status_code == 404
    return {
        "maintenance_recovery": "PASS",
        "maintenance_trip_cost_separation": "PASS",
        "restored_defect_replay": "PASS",
    }
