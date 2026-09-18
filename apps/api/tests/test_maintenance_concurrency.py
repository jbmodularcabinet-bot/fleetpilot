"""Batch 12 verification: competing operators and dispatch share the safety lock."""

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from fleetpilot.main import app

from .conftest import login
from .test_maintenance import transition, work
from .test_master_data import fleet
from .test_trips import create_trip

pytestmark = pytest.mark.asyncio


async def test_two_operators_overlapping_downtime(client, admin_db):
    await login(client)
    data = await fleet(client)
    vid = data["vehicles"]["id"]
    a, b = await work(client, vid), await work(client, vid)
    await admin_db.execute(
        text(
            "UPDATE organization_memberships SET role='MAINTENANCE' WHERE user_id=(SELECT id FROM users WHERE email='juan@example.com')"
        )
    )
    await admin_db.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": "http://localhost:3000"},
    ) as operator:
        await login(operator, "juan@example.com")
        a, b = await asyncio.gather(
            transition(client, a, "start"), transition(operator, b, "start")
        )
        assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] == "MAINTENANCE"
        await transition(
            client,
            a,
            "complete",
            odometer_at_completion="0",
            work_performed="First operator finished",
        )
        assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] == "MAINTENANCE"
        await transition(
            operator,
            b,
            "complete",
            odometer_at_completion="0",
            work_performed="Second operator finished",
        )
    assert (await client.get("/api/v1/vehicles/" + vid)).json()["status"] == "AVAILABLE"
    assert (
        await admin_db.scalar(
            text(
                "SELECT count(DISTINCT actor_id) FROM maintenance_events WHERE action='work_order.started'"
            )
        )
        == 2
    )


async def test_dispatch_cannot_race_maintenance_start(client):
    await login(client)
    data = await fleet(client)
    trip = await create_trip(client, data)
    w = await work(client, data["vehicles"]["id"])
    start, dispatch = await asyncio.gather(
        client.post(
            f"/api/v1/maintenance/work-orders/{w['id']}/start",
            json={"expected_version": 1},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        ),
        client.post(
            f"/api/v1/trips/{trip['id']}/transition",
            json={"action": "dispatch", "expected_version": trip["version"]},
        ),
    )
    assert sorted([start.status_code, dispatch.status_code]) == [200, 409], [
        start.text,
        dispatch.text,
    ]
    vehicle = (await client.get("/api/v1/vehicles/" + data["vehicles"]["id"])).json()
    state = (await client.get("/api/v1/trips/" + trip["id"])).json()
    order = (await client.get("/api/v1/maintenance/work-orders/" + w["id"])).json()
    if start.status_code == 200:
        assert (
            vehicle["status"] == "MAINTENANCE"
            and order["status"] == "IN_PROGRESS"
            and state["current_status"] == "SCHEDULED"
        )
    else:
        assert (
            vehicle["status"] != "MAINTENANCE"
            and order["status"] == "OPEN"
            and state["current_status"] == "DISPATCHED"
        )
