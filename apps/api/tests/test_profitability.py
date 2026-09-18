import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context
from fleetpilot.profitability import calculate
from fleetpilot.trip_lifecycle import ACTIONS

from .conftest import login
from .test_adjustments import adjustment, apply, reverse
from .test_expenses import cost, submit
from .test_maintenance import post as maintenance_post
from .test_maintenance import transition, work
from .test_sync import setup
from .test_trips import act


async def post(c, path, data, key=None):
    return await c.post(
        "/api/v1" + path, json=data, headers={"Idempotency-Key": key or str(uuid.uuid4())}
    )


async def revenue(c, trip, amount="25000.00", **extra):
    response = await post(
        c,
        f"/trips/{trip['id']}/revenue",
        dict(revenue_type="BASE_TRIP_CHARGE", amount=amount, **extra),
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]["revenue"]


async def review(c, item):
    r = await post(c, f"/trip-revenue/{item['id']}/review", {"expected_sequence": item["sequence"]})
    assert r.status_code == 200, r.text
    return r.json()["result"]["revenue"]


async def financial(c, trip):
    r = await c.get(f"/api/v1/trips/{trip['id']}/financials")
    assert r.status_code == 200, r.text
    return r.json()


async def fixture(c, close=True):
    trip, driver, data = await setup(c)
    ids = []
    for entry in [
        cost("FUEL", amount=None, liters="100", price_per_liter="65"),
        cost(amount="1000.00"),
        cost("PARKING", amount="200.00"),
        cost("DRIVER_ALLOWANCE", amount="1500.00"),
        cost("LOADING_FEE", amount="800.00"),
        cost("OTHER", amount="300.00", description="Handling fee"),
    ]:
        r = await submit(c, trip, entry)
        assert r.status_code == 200, r.text
        result = r.json()["result"]
        ids.append(result["expense"]["id"])
        trip["version"] = result["trip_version"]
    await login(c)
    for identifier in ids:
        r = await post(c, f"/expenses/{identifier}/review", dict(expected_version=trip["version"]))
        assert r.status_code == 200, r.text
        trip["version"] = r.json()["result"]["trip_version"]
    if close:
        for action in list(ACTIONS)[1:]:
            trip = await act(c, trip, action)
        r = await c.post(
            f"/api/v1/trips/{trip['id']}/complete",
            json=dict(expected_version=trip["version"], closeout_reviewed=True),
        )
        assert r.status_code == 200, r.text
        trip = r.json()
    return trip, ids, driver, data


@pytest.mark.asyncio
async def test_golden_adjustments_maintenance_and_reversal(client, admin_db):
    trip, ids, _, data = await fixture(client)
    item = await revenue(client, trip)
    assert (await financial(client, trip))["status"] == "PROVISIONAL"
    item = await review(client, item)
    # Batch 14 tightens FINAL: preserve the golden arithmetic and explicitly approve.
    result = await post(
        client,
        f"/trips/{trip['id']}/financial-review/approve",
        dict(
            expected_event_id=(
                await client.get(f"/api/v1/trips/{trip['id']}/financial-review")
            ).json()["latest_event_id"],
            records_confirmed=True,
        ),
    )
    assert result.status_code == 200, result.text
    f = await financial(client, trip)
    assert (
        f["revenue"]["effective_total"],
        f["direct_cost"]["effective_total"],
        f["contribution_amount"],
        f["contribution_margin_percent"],
        f["status"],
    ) == ("25000.00", "10300.00", "14700.00", "58.80", "FINAL")
    assert (await apply(client, trip, adjustment(ids[1], value="1500.00"))).status_code == 200
    f = await financial(client, trip)
    assert (
        f["direct_cost"]["effective_total"],
        f["contribution_amount"],
        f["contribution_margin_percent"],
    ) == ("10800.00", "14200.00", "56.80")
    key = str(uuid.uuid4())
    payload = adjustment(item["id"], value="26000.00")
    results = await asyncio.gather(
        *(post(client, f"/trip-revenue/{item['id']}/correct", payload, key) for _ in range(2))
    )
    assert {r.json()["outcome"] for r in results} == {"APPLIED", "ALREADY_APPLIED"}, [
        r.text for r in results
    ]
    aid = results[0].json()["result"]["adjustment_id"]
    assert (await financial(client, trip))["contribution_amount"] == "15200.00"
    original = (await client.get("/api/v1/trip-revenue/" + item["id"])).json()
    assert (
        original["amount"] == "25000.00"
        and original["effective_amount"] == "26000.00"
        and len(original["history"]) == 1
    )
    w = await work(client, data["vehicles"]["id"], trip_id=trip["id"])
    w = await transition(client, w, "start")
    await maintenance_post(
        client,
        f"/maintenance/work-orders/{w['id']}/cost-items",
        dict(type="PART", description="Repair parts", unit_cost="12000.00"),
    )
    assert (await financial(client, trip))["direct_cost"]["effective_total"] == "10800.00"
    assert (await reverse(client, aid, 1)).status_code == 200
    assert (await financial(client, trip))["revenue"]["effective_total"] == "25000.00"
    assert (await client.get(f"/api/v1/trips/{trip['id']}")).json() == trip
    assert (await client.get("/api/v1/expenses/" + ids[1])).json()["current"]["amount"] == "1000.00"
    assert (
        await admin_db.scalar(
            text("SELECT count(*) FROM audit_logs WHERE action='trip_revenue.corrected'")
        )
        == 2
    )
    owner = (await client.get("/api/v1/me")).json()
    async with Session() as db:
        await set_context(db, owner["user"]["id"], owner["organization"]["id"])
        for sql in [
            "UPDATE trip_revenue SET amount=amount+1",
            "UPDATE revenue_effective_values SET amount=1",
        ]:
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(text(sql))
    with pytest.raises(DBAPIError):
        async with admin_db.begin_nested():
            await admin_db.execute(text("UPDATE closed_trip_adjustments SET reason=reason"))


@pytest.mark.asyncio
async def test_reviewed_basis_void_advances_and_pending(client):
    trip, _, _ = await setup(client)
    for entry in [cost(amount="1000.00"), cost("DRIVER_CASH_ADVANCE", amount="9000.00")]:
        r = await submit(client, trip, entry)
        assert r.status_code == 200, r.text
        trip["version"] = r.json()["result"]["trip_version"]
    await login(client)
    item = await revenue(client, trip, "10000.00")
    await review(client, item)
    f = await financial(client, trip)
    assert (
        f["status"] == "PROVISIONAL"
        and f["direct_cost"]["submitted_total"] == "1000.00"
        and f["direct_cost"]["effective_total"] == "0.00"
        and f["excluded_cash_advances"] == "9000.00"
    )
    r = await post(
        client,
        f"/trip-revenue/{item['id']}/void",
        dict(expected_sequence=0, reason="Charge entered in error."),
    )
    assert r.status_code == 200, r.text
    f = await financial(client, trip)
    assert f["revenue"]["effective_total"] == "0.00" and f["contribution_margin_percent"] is None


@pytest.mark.parametrize("value", [1.2, "-1", "0", "1e3", "NaN", "10000000.01", "0.001"])
@pytest.mark.asyncio
async def test_invalid_money(client, value):
    trip, _, _ = await setup(client)
    await login(client)
    r = await post(
        client, f"/trips/{trip['id']}/revenue", dict(revenue_type="BASE_TRIP_CHARGE", amount=value)
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("organization_id", str(uuid.uuid4())),
        ("created_by", str(uuid.uuid4())),
        ("reviewed_by", str(uuid.uuid4())),
        ("effective_total", "999"),
        ("contribution", "999"),
        ("margin", "99"),
        ("status", "REVIEWED"),
    ],
)
@pytest.mark.asyncio
async def test_mass_assignment(client, field, value):
    trip, _, _ = await setup(client)
    await login(client)
    r = await post(
        client,
        f"/trips/{trip['id']}/revenue",
        dict(revenue_type="BASE_TRIP_CHARGE", amount="1.00", **{field: value}),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tenant_role_and_direct_rls(client, admin_db):
    trip, driver, data = await setup(client)
    await login(client)
    owner = (await client.get("/api/v1/me")).json()
    item = await revenue(client, trip)
    adjusted = await post(
        client, f"/trip-revenue/{item['id']}/correct", adjustment(item["id"], value="26000.00")
    )
    assert adjusted.status_code == 200, adjusted.text
    for email, code in [("other-owner@example.com", 404), ("juan@example.com", 403)]:
        await login(client, email)
        identity = (await client.get("/api/v1/me")).json()
        for path in [
            f"/trip-revenue/{item['id']}",
            f"/trips/{trip['id']}/revenue",
            f"/trips/{trip['id']}/financials",
            f"/trips/{trip['id']}/profitability",
        ]:
            assert (await client.get("/api/v1" + path)).status_code == code
        for path, payload in [
            (f"/trip-revenue/{item['id']}/review", dict(expected_sequence=1)),
            (
                f"/trip-revenue/{item['id']}/void",
                dict(expected_sequence=1, reason="Wrong tenant request"),
            ),
            (f"/trip-revenue/{item['id']}/correct", adjustment(item["id"], 1, value="27000.00")),
            (f"/trips/{trip['id']}/revenue", dict(revenue_type="SURCHARGE", amount="1.00")),
        ]:
            assert (await post(client, path, payload)).status_code == code
        listing = await client.get(
            "/api/v1/profitability/trips", params={"search": trip["trip_number"]}
        )
        assert listing.status_code == (200 if code == 404 else 403)
        if code == 404:
            assert listing.json()["total"] == 0
        async with Session() as db:
            await set_context(db, identity["user"]["id"], identity["organization"]["id"])
            for table in ["trip_revenue", "revenue_effective_values", "closed_trip_adjustments"]:
                assert await db.scalar(text("SELECT count(*) FROM " + table)) == 0
    await login(client)
    await admin_db.execute(
        text("UPDATE organization_memberships SET role='DISPATCHER' WHERE user_id=:u"),
        {"u": uuid.UUID(owner["user"]["id"])},
    )
    await admin_db.commit()
    assert (await client.get("/api/v1/profitability/trips")).status_code == 403
    assert (
        await post(
            client, f"/trips/{trip['id']}/revenue", dict(revenue_type="SURCHARGE", amount="1.00")
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_filters_pagination_and_sort(client):
    trip, _, data = await setup(client)
    await login(client)
    await review(client, await revenue(client, trip))
    for params in [
        {"customer_id": data["customers"]["id"]},
        {"driver_id": data["drivers"]["id"]},
        {"vehicle_id": data["vehicles"]["id"]},
        {"date_from": "2030-01-01T00:00:00Z", "date_to": "2030-12-31T23:59:59Z"},
        {"status": "DISPATCHED", "sort": "trip_number", "direction": "asc"},
    ]:
        r = await client.get("/api/v1/profitability/trips", params=params)
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1
    assert (await client.get("/api/v1/profitability/trips?limit=1&offset=1")).json()["items"] == []
    assert (await client.get("/api/v1/profitability/trips?sort=amount;DROP")).status_code == 422
    assert (await client.get("/api/v1/profitability/trips?date_from=2030-01-01")).status_code == 422


@pytest.mark.asyncio
async def test_correction_validation_void_reversal_atomicity(client, monkeypatch):
    from fleetpilot import financial_routes

    trip, _, _ = await setup(client)
    await login(client)
    item = await revenue(client, trip)
    path = f"/trip-revenue/{item['id']}/correct"
    assert (await post(client, path, adjustment(item["id"], reason="   "))).status_code == 422
    assert (await post(client, path, adjustment(str(uuid.uuid4())))).status_code == 404
    assert (await post(client, path, adjustment(item["id"], 1))).status_code == 409

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic audit failure")

    with monkeypatch.context() as m:
        m.setattr(financial_routes, "record", fail)
        assert (await post(client, path, adjustment(item["id"]))).status_code == 500
    assert (await client.get("/api/v1/trip-revenue/" + item["id"])).json()["sequence"] == 0
    r = await post(client, path, adjustment(item["id"], kind="VOID_ADJUSTMENT", value=None))
    assert r.status_code == 200, r.text
    assert (await post(client, path, adjustment(item["id"], 1))).status_code == 409
    assert (await reverse(client, r.json()["result"]["adjustment_id"], 1)).status_code == 200
    assert (await reverse(client, r.json()["result"]["adjustment_id"], 2)).status_code == 409


@pytest.mark.parametrize(
    "rev,cost,contribution,margin",
    [
        ("25000.00", "10300.00", "14700.00", "58.80"),
        ("0.00", "1000.00", "-1000.00", None),
        ("10000.00", "12500.00", "-2500.00", "-25.00"),
        ("0.30", "0.10", "0.20", "66.67"),
    ],
)
def test_exact_contribution(rev, cost, contribution, margin):
    def row(category, value):
        return dict(
            category=category,
            submitted_total=Decimal(value),
            reviewed_total=Decimal(value),
            unreviewed_count=0,
            reviewed_count=1,
        )

    f = calculate(
        {"id": "test", "current_status": "COMPLETED"},
        [row("BASE_TRIP_CHARGE", rev)],
        [row("TOLL", cost)],
    )
    assert f["contribution_amount"] == contribution and f["contribution_margin_percent"] == margin


@pytest.mark.asyncio
async def test_exact_maintenance_exclusion_case(client):
    trip, _, data = await setup(client)
    result = await submit(client, trip, cost(amount="10000.00"))
    assert result.status_code == 200
    item = result.json()["result"]
    trip["version"] = item["trip_version"]
    await login(client)
    result = await post(
        client, f"/expenses/{item['expense']['id']}/review", dict(expected_version=trip["version"])
    )
    assert result.status_code == 200, result.text
    trip["version"] = result.json()["result"]["trip_version"]
    await review(client, await revenue(client, trip))
    w = (
        await maintenance_post(
            client,
            "/maintenance/work-orders",
            dict(
                vehicle_id=data["vehicles"]["id"],
                trip_id=trip["id"],
                type="REPAIR",
                title="Separate service",
                description="Separate maintenance cost",
                requires_vehicle_downtime=False,
            ),
        )
    )["result"]["work_order"]
    await maintenance_post(
        client,
        f"/maintenance/work-orders/{w['id']}/cost-items",
        dict(type="PART", description="Separate service", unit_cost="12000.00"),
    )
    f = await financial(client, trip)
    assert (
        f["direct_cost"]["effective_total"] == "10000.00" and f["contribution_amount"] == "15000.00"
    )


@pytest.mark.asyncio
async def test_revenue_text_correction_other_and_closed_void(client):
    trip, _, _, _ = await fixture(client)
    response = await post(
        client, f"/trips/{trip['id']}/revenue", dict(revenue_type="OTHER", amount="1.00")
    )
    assert response.status_code == 422
    item = await revenue(client, trip, "0.10")
    item = await review(client, item)
    for sequence, kind, value in [
        (0, "REFERENCE_CORRECTION", "CHARGE-001"),
        (1, "DESCRIPTION_CORRECTION", "Operational surcharge"),
    ]:
        r = await post(
            client,
            f"/trip-revenue/{item['id']}/correct",
            adjustment(item["id"], sequence, kind, value),
        )
        assert r.status_code == 200, r.text
    assert (
        await post(
            client,
            f"/trip-revenue/{item['id']}/void",
            dict(expected_sequence=2, reason="Void after completion."),
        )
    ).status_code == 409
    r = await post(
        client,
        f"/trip-revenue/{item['id']}/correct",
        adjustment(item["id"], 2, "VOID_ADJUSTMENT", None),
    )
    assert r.status_code == 200, r.text
    assert (await financial(client, trip))["revenue"]["effective_total"] == "0.00"
    assert (await reverse(client, r.json()["result"]["adjustment_id"], 3)).status_code == 200
    assert (await financial(client, trip))["revenue"]["effective_total"] == "0.10"


@pytest.mark.parametrize("role", ["OWNER", "ADMIN", "MANAGER", "ACCOUNTING"])
@pytest.mark.asyncio
async def test_authorized_roles_and_restrictive_overrides(client, admin_db, role):
    trip, _, _ = await setup(client)
    await login(client)
    identity = (await client.get("/api/v1/me")).json()
    params = {"u": uuid.UUID(identity["user"]["id"]), "role": role}
    await admin_db.execute(
        text("UPDATE organization_memberships SET role=:role WHERE user_id=:u"), params
    )
    await admin_db.commit()
    item = await revenue(client, trip)
    await review(client, item)
    assert (await financial(client, trip))["revenue"]["effective_total"] == "25000.00"
    await admin_db.execute(
        text(
            'UPDATE organization_memberships SET permissions_json=\'{"deny":["trip_profitability.read"]}\'::jsonb WHERE user_id=:u'
        ),
        params,
    )
    await admin_db.commit()
    assert (await client.get(f"/api/v1/trips/{trip['id']}/financials")).status_code == 403
