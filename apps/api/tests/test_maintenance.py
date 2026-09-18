import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from fleetpilot.maintenance_schemas import CostInput, next_due, schedule_state

from .conftest import login
from .delivery_helpers import image_bytes
from .test_master_data import DATA, assign, fleet
from .test_trips import body


@pytest.mark.parametrize(
    "reading,expected",
    [
        ("48000", "OK"),
        ("48900", "OK"),
        ("49000", "UPCOMING"),
        ("49100", "UPCOMING"),
        ("50000", "DUE"),
        ("50100", "OVERDUE"),
    ],
)
def test_odometer_thresholds(reading, expected):
    assert (
        schedule_state(
            {"next_due_odometer": Decimal("50000"), "warning_km": 1000},
            Decimal(reading),
            date.today(),
        )
        == expected
    )


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 6, 1), "OK"),
        (date(2026, 6, 16), "UPCOMING"),
        (date(2026, 6, 30), "DUE"),
        (date(2026, 7, 1), "OVERDUE"),
    ],
)
def test_date_thresholds(day, expected):
    due = next_due(dict(last_service_at=date(2026, 1, 1), date_interval_days=180))
    assert due["next_due_at"] == date(2026, 6, 30)
    assert schedule_state({**due, "warning_days": 14}, Decimal(0), day) == expected


@pytest.mark.parametrize("reading,day", [("50001", date(2026, 1, 1)), ("1", date(2027, 1, 1))])
def test_combined_either(reading, day):
    assert (
        schedule_state(
            dict(
                next_due_odometer=Decimal(50000),
                next_due_at=date(2026, 6, 30),
                warning_km=1000,
                warning_days=14,
            ),
            Decimal(reading),
            day,
        )
        == "OVERDUE"
    )


def test_cost_decimal():
    values = [
        CostInput(type=k, description=k, unit_cost=v).total
        for k, v in [("PART", "1234.56"), ("LABOR", "500.00"), ("OTHER", "100.10")]
    ]
    assert sum(values) == Decimal("1834.66")
    assert CostInput(
        type="PART", description="Round", quantity="1", unit_cost="0.005"
    ).total == Decimal("0.01")


@pytest.mark.parametrize("value", [1.2, "-1", "1e3", "999999999999", "0.12345"])
def test_invalid_money(value):
    with pytest.raises(ValueError):
        CostInput(type="PART", description="Part", unit_cost=value)


async def post(client, path, data, key=None, expected=200):
    r = await client.post(
        "/api/v1" + path, json=data, headers={"Idempotency-Key": key or str(uuid.uuid4())}
    )
    assert r.status_code == expected, r.text
    return r.json()


async def work(client, vehicle, **extra):
    return (
        await post(
            client,
            "/maintenance/work-orders",
            dict(
                vehicle_id=vehicle,
                type="PREVENTIVE",
                title="Oil service",
                description="Replace engine oil",
                requires_vehicle_downtime=True,
                **extra,
            ),
        )
    )["result"]["work_order"]


async def transition(client, w, action, **extra):
    return (
        await post(
            client,
            f"/maintenance/work-orders/{w['id']}/{action}",
            dict(expected_version=w["version"], **extra),
        )
    )["result"]["work_order"]


@pytest.mark.asyncio
async def test_preventive_golden_and_cost_separation(client, admin_db):
    await login(client)
    data = await fleet(client)
    vid = data["vehicles"]["id"]
    await client.patch("/api/v1/vehicles/" + vid, json={**DATA["vehicles"], "odometer": "48000"})
    sch = await post(
        client,
        f"/vehicles/{vid}/maintenance-schedules",
        dict(
            service_type="ENGINE_OIL",
            interval_type="ODOMETER",
            odometer_interval_km=5000,
            last_service_odometer="45000",
            warning_km=1000,
        ),
    )
    assert sch["next_due_odometer"] == "50000.0"
    for odo, state in [("49100", "UPCOMING"), ("50100", "OVERDUE")]:
        assert (
            await client.patch(
                "/api/v1/vehicles/" + vid, json={**DATA["vehicles"], "odometer": odo}
            )
        ).status_code == 200
        assert (await client.get(f"/api/v1/vehicles/{vid}/maintenance")).json()["schedules"][0][
            "due_status"
        ] == state
    w = await work(client, vid, maintenance_schedule_id=sch["id"])
    w = await transition(client, w, "start")
    assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] == "MAINTENANCE"
    r = await client.post(
        "/api/v1/trips", json=body(data, vehicle_id=vid, driver_id=data["drivers"]["id"])
    )
    assert r.status_code == 409
    for kind, amount in [("PART", "1234.56"), ("LABOR", "500.00"), ("OTHER", "100.10")]:
        await post(
            client,
            f"/maintenance/work-orders/{w['id']}/cost-items",
            dict(type=kind, description=kind, unit_cost=amount),
        )
    r = await client.post(
        f"/api/v1/maintenance/work-orders/{w['id']}/evidence?filename=photo.png&evidence_type=MAINTENANCE_RECEIPT",
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, r.text
    evidence = r.json()["result"]["evidence_id"]
    assert (await client.get("/api/v1/maintenance-evidence/" + evidence)).status_code == 200
    w = await transition(
        client,
        w,
        "complete",
        odometer_at_completion="50250",
        work_performed="Oil and filter replaced",
    )
    assert w["total_cost"] == "1834.66"
    history = (await client.get(f"/api/v1/vehicles/{vid}/maintenance")).json()
    assert history["schedules"][0]["next_due_odometer"] == "55250.0"
    assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] == "AVAILABLE"
    assert await admin_db.scalar(text("SELECT count(*) FROM trip_expenses")) == 0
    assert (
        await admin_db.scalar(
            text("SELECT count(*) FROM audit_logs WHERE action='work_order.completed'")
        )
        == 1
    )
    await post(
        client,
        f"/maintenance/work-orders/{w['id']}/start",
        dict(expected_version=w["version"]),
        expected=409,
    )
    await post(
        client,
        f"/maintenance/work-orders/{w['id']}/cost-items",
        dict(type="PART", description="late", unit_cost="1"),
        expected=409,
    )


@pytest.mark.asyncio
async def test_multiple_blockers_and_cancellation(client):
    await login(client)
    data = await fleet(client)
    vid = data["vehicles"]["id"]
    a = await transition(client, await work(client, vid), "start")
    b = await transition(client, await work(client, vid), "start")
    await post(
        client,
        f"/maintenance/work-orders/{a['id']}/cancel",
        dict(expected_version=a["version"], reason="Cancelled by operator"),
        expected=409,
    )
    await transition(
        client, a, "complete", odometer_at_completion="0", work_performed="First finished"
    )
    assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] == "MAINTENANCE"
    await transition(
        client, b, "complete", odometer_at_completion="0", work_performed="Second finished"
    )
    assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] == "AVAILABLE"
    c = await work(client, vid)
    await transition(client, c, "cancel", reason="No service needed")
    assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] == "AVAILABLE"


@pytest.mark.asyncio
async def test_defect_replay_review_repair_and_ownership(client, admin_db):
    await login(client, "juan@example.com")
    user = (await client.get("/api/v1/me")).json()["user"]["id"]
    await login(client)
    data = await fleet(client)
    vid = data["vehicles"]["id"]
    assert (
        await client.patch(
            "/api/v1/drivers/" + data["drivers"]["id"], json={**DATA["drivers"], "user_id": user}
        )
    ).status_code == 200
    assert (await assign(client, data)).status_code == 201
    await login(client, "juan@example.com")
    payload = dict(
        vehicle_id=vid,
        severity="SERIOUS",
        category="BRAKES",
        description="Brake pedal feels softer than normal.",
        reported_at_client=datetime.now(timezone.utc).isoformat(),
    )
    key = str(uuid.uuid4())
    result = await post(client, "/driver/defects", payload, key)
    item = result["result"]["defect"]
    again = await post(client, "/driver/defects", payload, key)
    assert again["outcome"] == "ALREADY_APPLIED" and again["result"]["defect"]["id"] == item["id"]
    photo_key = str(uuid.uuid4())
    url = f"/api/v1/defects/{item['id']}/evidence?filename=photo.png"
    evidence = []
    for _ in range(2):
        r = await client.post(
            url,
            content=image_bytes(),
            headers={"Content-Type": "image/png", "Idempotency-Key": photo_key},
        )
        assert r.status_code == 200, r.text
        evidence.append(r.json()["result"]["evidence_id"])
    assert evidence[0] == evidence[1]
    await post(
        client, f"/defects/{item['id']}/review", {"reason": "Driver cannot review"}, expected=403
    )
    await login(client)
    await post(client, f"/defects/{item['id']}/review", {"reason": "Inspection needed"})
    w = await work(client, vid, defect_report_id=item["id"])
    w = await transition(client, w, "start")
    await transition(
        client, w, "complete", odometer_at_completion="0", work_performed="Brake issue repaired"
    )
    actual = (await client.get("/api/v1/defects/" + item["id"])).json()
    assert actual["status"] == "RESOLVED" and actual["description"] == payload["description"]
    assert len(actual["evidence"]) == 1
    await login(client, "other-owner@example.com")
    for path in [
        f"/defects/{item['id']}",
        f"/maintenance/work-orders/{w['id']}",
        f"/maintenance-evidence/{evidence[0]}",
        f"/vehicles/{vid}/maintenance",
    ]:
        assert (await client.get("/api/v1" + path)).status_code == 404
