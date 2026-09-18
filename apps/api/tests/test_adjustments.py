import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context
from fleetpilot.trip_lifecycle import ACTIONS

from .conftest import login
from .test_expenses import cost, submit
from .test_sync import setup
from .test_trips import act

pytestmark = pytest.mark.asyncio


async def completed(client):
    trip, driver, fleet = await setup(client)
    ids = []
    for data in [
        cost("FUEL", amount=None, liters="50", price_per_liter="60", odometer="12500"),
        cost(amount="300.00"),
        cost("PARKING", amount="100.00"),
    ]:
        response = await submit(client, trip, data)
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        ids.append(result["expense"]["id"])
        trip["version"] = result["trip_version"]
    await client.post("/api/v1/auth/logout")
    await login(client)
    for action in list(ACTIONS)[1:]:
        trip = await act(client, trip, action)
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/complete",
        json={"expected_version": trip["version"], "closeout_reviewed": True},
    )
    assert response.status_code == 200, response.text
    return response.json(), ids, driver, fleet


def adjustment(
    target,
    sequence=0,
    kind="AMOUNT_CORRECTION",
    value="350.00",
    reason="Receipt verified after trip close.",
):
    return dict(
        target_id=target,
        expected_sequence=sequence,
        adjustment_type=kind,
        new_value=value,
        reason=reason,
    )


async def apply(client, trip, data, key=None):
    return await client.post(
        f"/api/v1/trips/{trip['id']}/adjustments",
        json=data,
        headers={"Idempotency-Key": key or str(uuid.uuid4())},
    )


async def reverse(client, identifier, sequence):
    return await client.post(
        f"/api/v1/adjustments/{identifier}/reverse",
        json={"expected_sequence": sequence, "reason": "Adjustment entered in error."},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )


async def test_golden_and_reversal_immutable_history(client, admin_db):
    trip, ids, _, _ = await completed(client)
    baseline = (await client.get(f"/api/v1/expenses/{ids[1]}")).json()
    milestones = (await client.get(f"/api/v1/trips/{trip['id']}/milestones")).json()
    key = str(uuid.uuid4())
    data = adjustment(ids[1])
    responses = await asyncio.gather(*(apply(client, trip, data, key) for _ in range(2)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert {r.json()["outcome"] for r in responses} == {"APPLIED", "ALREADY_APPLIED"}
    item = responses[0].json()["result"]
    assert item["effective"]["amount"] == "350.00"
    assert (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()[
        "submitted_total"
    ] == "3450.00"
    current = (await client.get(f"/api/v1/expenses/{ids[1]}")).json()
    assert (
        current["current"] == baseline["current"] and current["revisions"] == baseline["revisions"]
    )
    assert (await client.get(f"/api/v1/trips/{trip['id']}")).json() == trip
    assert (await client.get(f"/api/v1/trips/{trip['id']}/milestones")).json() == milestones
    r = await reverse(client, item["adjustment_id"], 1)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["effective"]["amount"] == "300.00"
    assert (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()[
        "submitted_total"
    ] == "3400.00"
    history = (await client.get(f"/api/v1/trips/{trip['id']}/adjustments")).json()
    assert [x["status"] for x in history["items"]] == ["REVERSED", "REVERSAL"]
    assert history["items"][0]["amount_delta"] == "50.00"
    assert (await reverse(client, item["adjustment_id"], 2)).status_code == 409
    actions = (
        (
            await admin_db.execute(
                text("SELECT action FROM audit_logs WHERE action LIKE 'closed_trip_adjustment.%'")
            )
        )
        .scalars()
        .all()
    )
    assert sorted(actions) == [
        "closed_trip_adjustment.applied",
        "closed_trip_adjustment.created",
        "closed_trip_adjustment.reversed",
    ]
    assert (
        await client.post(
            f"/api/v1/expenses/{ids[1]}/correct",
            json={**cost(), "expected_version": trip["version"], "reason": "No ordinary override"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
    ).status_code == 409


@pytest.mark.parametrize(
    "value", [350.0, -50, "-50.00", "0.00", "10000000.01", "1e3", "0.001", "NaN"]
)
async def test_bad_decimal(client, value):
    trip, ids, _, _ = await completed(client)
    assert (await apply(client, trip, adjustment(ids[1], value=value))).status_code == 422


@pytest.mark.parametrize("reason", ["", "          ", "short", "a b c d e"])
async def test_reason_validation(client, reason):
    trip, ids, _, _ = await completed(client)
    assert (await apply(client, trip, adjustment(ids[1], reason=reason))).status_code == 422


async def test_multiple_centavo_adjustments_lifo_and_void(client):
    trip, ids, _, _ = await completed(client)
    first = (await apply(client, trip, adjustment(ids[1], value="300.01"))).json()["result"]
    second = (await apply(client, trip, adjustment(ids[1], 1, value="300.02"))).json()["result"]
    assert (await reverse(client, first["adjustment_id"], 2)).status_code == 409
    assert (await reverse(client, second["adjustment_id"], 2)).json()["result"]["effective"][
        "amount"
    ] == "300.01"
    assert (await reverse(client, first["adjustment_id"], 3)).json()["result"]["effective"][
        "amount"
    ] == "300.00"
    void = (
        await apply(client, trip, adjustment(ids[1], 4, kind="VOID_ADJUSTMENT", value=None))
    ).json()["result"]
    assert (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()[
        "submitted_total"
    ] == "3100.00"
    assert (await apply(client, trip, adjustment(ids[1], 5))).status_code == 409
    assert (await reverse(client, void["adjustment_id"], 5)).status_code == 200


@pytest.mark.parametrize(
    "kind,value,field",
    [
        ("REFERENCE_CORRECTION", "Receipt-99", "reference_number"),
        ("DESCRIPTION_CORRECTION", "Verified receipt details", "description"),
        ("ODOMETER_CORRECTION", "12000.0", "odometer"),
    ],
)
async def test_metadata_and_odometer_do_not_change_vehicle(client, admin_db, kind, value, field):
    trip, ids, _, fleet = await completed(client)
    before = (
        await admin_db.execute(
            text("SELECT odometer,reviewed_fuel_odometer FROM vehicles WHERE id=:id"),
            {"id": uuid.UUID(fleet["vehicles"]["id"])},
        )
    ).one()
    r = await apply(client, trip, adjustment(ids[0], kind=kind, value=value))
    assert r.status_code == 200, r.text
    assert (await client.get(f"/api/v1/expenses/{ids[0]}")).json()["effective"][field] == value
    after = (
        await admin_db.execute(
            text("SELECT odometer,reviewed_fuel_odometer FROM vehicles WHERE id=:id"),
            {"id": uuid.UUID(fleet["vehicles"]["id"])},
        )
    ).one()
    assert before == after
    assert (await reverse(client, r.json()["result"]["adjustment_id"], 1)).status_code == 200


async def test_roles_tenant_target_and_direct_rls(client, admin_db):
    trip, ids, driver, _ = await completed(client)
    owner = (await client.get("/api/v1/me")).json()
    r = await apply(client, trip, adjustment(ids[1]))
    assert r.status_code == 200, r.text
    adjustment_id = r.json()["result"]["adjustment_id"]
    for role in ("DISPATCHER", "DRIVER", "MANAGER", "ACCOUNTING"):
        await admin_db.execute(
            text(
                "UPDATE organization_memberships SET role=:role WHERE user_id=:user AND organization_id=:org"
            ),
            {
                "role": role,
                "user": uuid.UUID(owner["user"]["id"]),
                "org": uuid.UUID(owner["organization"]["id"]),
            },
        )
        await admin_db.commit()
        assert (await apply(client, trip, adjustment(ids[1], 1))).status_code == 403
        assert (await client.get(f"/api/v1/trips/{trip['id']}/adjustments")).status_code == 403
        assert (await reverse(client, adjustment_id, 1)).status_code == 403
    await admin_db.execute(
        text(
            "UPDATE organization_memberships SET role='ADMIN' WHERE user_id=:user AND organization_id=:org"
        ),
        {"user": uuid.UUID(owner["user"]["id"]), "org": uuid.UUID(owner["organization"]["id"])},
    )
    await admin_db.commit()
    assert (await apply(client, trip, adjustment(ids[1], 1, value="351.00"))).status_code == 200
    assert (await apply(client, trip, adjustment(str(uuid.uuid4())))).status_code == 404
    async with Session() as db:
        await set_context(db, owner["user"]["id"], owner["organization"]["id"])
        result = await db.execute(text("UPDATE closed_trip_adjustments SET reason=reason"))
        assert result.rowcount == 0  # No UPDATE RLS policy; history stays unchanged.
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text("UPDATE expense_effective_values SET amount=amount"))
    with pytest.raises(DBAPIError):
        async with admin_db.begin_nested():
            await admin_db.execute(text("UPDATE closed_trip_adjustments SET reason=reason"))
    await client.post("/api/v1/auth/logout")
    await login(client, "other-owner@example.com")
    other = (await client.get("/api/v1/me")).json()
    assert (await client.get(f"/api/v1/trips/{trip['id']}/adjustments")).status_code == 404
    assert (await apply(client, trip, adjustment(ids[1], 2))).status_code == 404
    assert (await reverse(client, adjustment_id, 2)).status_code == 404
    async with Session() as db:
        await set_context(db, other["user"]["id"], other["organization"]["id"])
        for table in ("closed_trip_adjustments", "expense_effective_values"):
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0
    await client.post("/api/v1/auth/logout")
    await login(client, "juan@example.com")
    assert (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()[
        "submitted_total"
    ] == "3451.00"
    async with Session() as db:
        await set_context(db, driver["user"]["id"], driver["organization"]["id"])
        assert await db.scalar(text("SELECT count(*) FROM closed_trip_adjustments")) == 0


async def test_stale_permission_and_atomic_failure(client, admin_db, monkeypatch):
    from fleetpilot import adjustment_routes

    trip, ids, _, _ = await completed(client)
    assert (await apply(client, trip, adjustment(ids[1], 1))).status_code == 409

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(adjustment_routes, "record", fail)
    assert (await apply(client, trip, adjustment(ids[1]))).status_code == 500
    assert (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()[
        "submitted_total"
    ] == "3400.00"
    assert await admin_db.scalar(text("SELECT count(*) FROM closed_trip_adjustments")) == 0
    assert await admin_db.scalar(text("SELECT count(*) FROM expense_effective_values")) == 0
