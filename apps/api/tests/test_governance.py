import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context
from fleetpilot.trip_lifecycle import ACTIONS

from .conftest import login
from .test_adjustments import adjustment, apply
from .test_expenses import cost, submit
from .test_profitability import financial, post, revenue, review
from .test_sync import setup
from .test_trips import act

REASON = "Receipt and cash verified by owner."


async def state(c, t):
    r = await c.get(f"/api/v1/trips/{t['id']}/financial-review")
    assert r.status_code == 200, r.text
    return r.json()


async def approve(c, t, key=None):
    s = await state(c, t)
    return await post(
        c,
        f"/trips/{t['id']}/financial-review/approve",
        dict(expected_event_id=s["latest_event_id"], records_confirmed=True),
        key,
    )


async def issue(c, t, amount="5000.00", **extra):
    r = await post(c, f"/trips/{t['id']}/cash-advances", dict(amount=amount, **extra))
    assert r.status_code == 200, r.text
    return r.json()["result"]["advance"]


async def cash(c, a, amount, key=None):
    return await post(
        c, f"/cash-advances/{a['id']}/cash-return", dict(amount=amount, reason=REASON), key
    )


async def allocate(c, a, e, key=None):
    return await post(
        c, f"/cash-advances/{a['id']}/apply-expense", dict(expense_id=e, reason=REASON), key
    )


async def fixture(c, partial=False):
    t, d, data = await setup(c)
    ids = []
    for entry in (
        [cost(amount="3000.00")]
        if partial
        else [cost("FUEL", amount=None, liters="50", price_per_liter="50"), cost(amount="700.00")]
    ):
        r = await submit(c, t, entry)
        assert r.status_code == 200, r.text
        t["version"] = r.json()["result"]["trip_version"]
        ids.append(r.json()["result"]["expense"]["id"])
    await login(c)
    for e in ids:
        r = await post(c, f"/expenses/{e}/review", dict(expected_version=t["version"]))
        assert r.status_code == 200, r.text
        t["version"] = r.json()["result"]["trip_version"]
    for action in list(ACTIONS)[1:]:
        t = await act(c, t, action)
    r = await c.post(
        f"/api/v1/trips/{t['id']}/complete",
        json=dict(expected_version=t["version"], closeout_reviewed=True),
    )
    assert r.status_code == 200, r.text
    t = r.json()
    await review(c, await revenue(c, t, "20000.00"))
    return t, ids, d, data


@pytest.mark.asyncio
async def test_settlement_review_invalidation_golden(client, admin_db):
    t, ids, _, _ = await fixture(client)
    a = await issue(client, t)
    assert a["status"] == "ISSUED" and a["outstanding"] == "5000.00"
    for e in ids:
        assert (await allocate(client, a, e)).status_code == 200
    r = await cash(client, a, "1800.00")
    assert r.status_code == 200, r.text
    a = r.json()["result"]["advance"]
    assert (a["applied"], a["returned"], a["outstanding"], a["status"]) == (
        "3200.00",
        "1800.00",
        "0.00",
        "SETTLED",
    )
    review_snapshot = await state(client, t)
    assert review_snapshot["status"] == "READY_FOR_REVIEW"
    assert review_snapshot["financials"]["contribution_amount"] == "16800.00"
    f = await financial(client, t)
    assert (
        f["direct_cost"]["effective_total"] == "3200.00"
        and f["contribution_amount"] == "16800.00"
        and f["status"] == "PROVISIONAL"
    )
    s = await state(client, t)
    started = await post(
        client,
        f"/trips/{t['id']}/financial-review/start",
        dict(expected_event_id=s["latest_event_id"], records_confirmed=True),
    )
    assert started.status_code == 200, started.text
    assert (await approve(client, t)).status_code == 200
    assert (await financial(client, t))["status"] == "FINAL"
    old = await state(client, t)
    assert (await apply(client, t, adjustment(ids[1], value="1200.00"))).status_code == 200
    assert (await financial(client, t))["status"] == "PROVISIONAL"
    assert (await financial(client, t))["contribution_amount"] == "16300.00"
    assert any(e["status"] == "APPROVED" for e in (await state(client, t))["history"])
    stale = await post(
        client,
        f"/trips/{t['id']}/financial-review/approve",
        dict(expected_event_id=old["latest_event_id"], records_confirmed=True),
    )
    assert stale.status_code == 409
    assert (await approve(client, t)).status_code == 200
    assert (await financial(client, t))["status"] == "FINAL"
    assert (await client.get(f"/api/v1/trips/{t['id']}")).json() == t
    fresh = (await client.get(f"/api/v1/trips/{t['id']}/cash-advances")).json()["items"][0]
    assert len(fresh["history"]) == 3 and fresh["outstanding"] == "0.00"
    actions = set((await admin_db.execute(text("SELECT action FROM audit_logs"))).scalars())
    assert {
        "cash_advance.created",
        "cash_advance.settlement_applied",
        "cash_advance.cash_returned",
        "cash_advance.settled",
        "financial_review.started",
        "financial_review.approved",
        "financial_review.invalidated",
    } <= actions


@pytest.mark.asyncio
async def test_partial_reversal_and_invalid_allocation(client):
    t, ids, _, _ = await fixture(client, True)
    a = await issue(client, t)
    assert (await allocate(client, a, ids[0])).status_code == 200
    r = await cash(client, a, "1000.00")
    a = r.json()["result"]["advance"]
    assert a["status"] == "PARTIALLY_SETTLED" and a["outstanding"] == "1000.00"
    assert (await approve(client, t)).status_code == 409
    assert (await cash(client, a, "1000.00")).status_code == 200
    assert (await approve(client, t)).status_code == 200
    assert (await apply(client, t, adjustment(ids[0], value="2500.00"))).status_code == 200
    assert (await approve(client, t)).status_code == 409
    entry = a["history"][0]
    r = await post(
        client, f"/cash-advances/{a['id']}/entries/{entry['id']}/reverse", dict(reason=REASON)
    )
    assert r.status_code == 200, r.text
    assert r.json()["result"]["advance"]["outstanding"] == "3000.00"
    assert (await allocate(client, a, ids[0])).status_code == 200
    assert (await cash(client, a, "500.00")).status_code == 200
    assert (await approve(client, t)).status_code == 200
    assert (await financial(client, t))["status"] == "FINAL"
    assert (
        await post(client, f"/cash-advances/{a['id']}/void", dict(reason=REASON))
    ).status_code == 409


@pytest.mark.asyncio
async def test_concurrency_idempotency_and_double_application(client):
    t, ids, _, _ = await fixture(client)
    a = await issue(client, t)
    results = await asyncio.gather(*(allocate(client, a, ids[0]) for _ in range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    results = await asyncio.gather(*(cash(client, a, "2000.00") for _ in range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    key = str(uuid.uuid4())
    results = await asyncio.gather(*(cash(client, a, "500.00", key) for _ in range(2)))
    assert {r.json()["outcome"] for r in results} == {"APPLIED", "ALREADY_APPLIED"}
    assert (await cash(client, a, "400.00", key)).status_code == 409
    key = str(uuid.uuid4())
    s = await state(client, t)
    payload = dict(expected_event_id=s["latest_event_id"], records_confirmed=True)
    results = await asyncio.gather(
        *(
            post(client, f"/trips/{t['id']}/financial-review/approve", payload, key)
            for _ in range(2)
        )
    )
    assert {r.json()["outcome"] for r in results} == {"APPLIED", "ALREADY_APPLIED"}


@pytest.mark.asyncio
async def test_legacy_reconciliation_void_and_exact_cents(client):
    t, _, _ = await setup(client)
    r = await submit(client, t, cost("DRIVER_CASH_ADVANCE", amount="10.01"))
    e = r.json()["result"]["expense"]["id"]
    t["version"] = r.json()["result"]["trip_version"]
    await login(client)
    r = await post(client, f"/trips/{t['id']}/cash-advances", dict(source_expense_id=e))
    assert r.status_code == 200, r.text
    a = r.json()["result"]["advance"]
    assert a["amount_issued"] == "10.01"
    assert (
        await post(client, f"/trips/{t['id']}/cash-advances", dict(source_expense_id=e))
    ).status_code == 409
    assert (await cash(client, a, "10.00")).status_code == 200
    assert (await cash(client, a, "0.01")).json()["result"]["advance"]["outstanding"] == "0.00"
    b = await issue(client, t, "1.00")
    r = await post(client, f"/cash-advances/{b['id']}/void", dict(reason=REASON))
    assert r.status_code == 200, r.text
    assert r.json()["result"]["advance"]["status"] == "VOIDED"
    assert (await cash(client, b, "0.01")).status_code == 409


@pytest.mark.parametrize("value", [1.2, "-1", "0", "1e3", "NaN", "10000000.01", "0.001"])
@pytest.mark.asyncio
async def test_cash_invalid_money(client, value):
    await login(client)
    r = await post(client, f"/trips/{uuid.uuid4()}/cash-advances", dict(amount=value))
    assert r.status_code == 422
    r = await post(
        client, f"/cash-advances/{uuid.uuid4()}/cash-return", dict(amount=value, reason=REASON)
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    "field", ["organization_id", "driver_id", "outstanding", "status", "issued_by", "reviewer"]
)
@pytest.mark.asyncio
async def test_cash_mass_assignment(client, field):
    await login(client)
    r = await post(
        client, f"/trips/{uuid.uuid4()}/cash-advances", dict(amount="1.00", **{field: "fake"})
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tenant_roles_rls_history(client, admin_db):
    t, ids, _, _ = await fixture(client)
    a = await issue(client, t)
    assert (await allocate(client, a, ids[0])).status_code == 200
    me = (await client.get("/api/v1/me")).json()
    async with Session() as db:
        await set_context(db, me["user"]["id"], me["organization"]["id"])
        for table in ("cash_advances", "cash_advance_settlement_entries"):
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(text(f"UPDATE {table} SET id=id"))
    await login(client, "juan@example.com")
    for path in (f"/trips/{t['id']}/cash-advances", f"/trips/{t['id']}/financial-review"):
        assert (await client.get("/api/v1" + path)).status_code == 403
    assert (await cash(client, a, "1.00")).status_code == 403
    assert (
        await post(
            client,
            f"/trips/{t['id']}/financial-review/approve",
            dict(expected_event_id=None, records_confirmed=True),
        )
    ).status_code == 403
    driver = (await client.get("/api/v1/me")).json()
    async with Session() as db:
        await set_context(db, driver["user"]["id"], driver["organization"]["id"])
        for table in (
            "cash_advances",
            "cash_advance_settlement_entries",
            "trip_financial_review_events",
        ):
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0
    # Seed's second tenant owner.
    await login(client, "other-owner@example.com")
    for path in (f"/trips/{t['id']}/cash-advances", f"/trips/{t['id']}/financial-review"):
        assert (await client.get("/api/v1" + path)).status_code == 404
    assert (await cash(client, a, "1.00")).status_code == 404
    other = (await client.get("/api/v1/me")).json()
    async with Session() as db:
        await set_context(db, other["user"]["id"], other["organization"]["id"])
        for table in (
            "cash_advances",
            "cash_advance_settlement_entries",
            "trip_financial_review_events",
        ):
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("OWNER", True),
        ("ADMIN", True),
        ("MANAGER", False),
        ("ACCOUNTING", False),
        ("DISPATCHER", False),
        ("DRIVER", False),
    ],
)
@pytest.mark.asyncio
async def test_approval_role_boundaries(client, admin_db, role, allowed):
    t, _, _, _ = await fixture(client)
    latest = (await state(client, t))["latest_event_id"]
    me = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text("UPDATE organization_memberships SET role=:role WHERE user_id=:id"),
        dict(role=role, id=uuid.UUID(me["user"]["id"])),
    )
    await admin_db.commit()
    r = await post(
        client,
        f"/trips/{t['id']}/financial-review/approve",
        dict(expected_event_id=latest, records_confirmed=True),
    )
    assert r.status_code == (200 if allowed else 403), r.text


@pytest.mark.asyncio
async def test_atomic_failure_and_approval_tampering(client, admin_db, monkeypatch):
    from fleetpilot import governance_routes

    t, _, _, _ = await fixture(client)
    a = await issue(client, t)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic audit failure")

    with monkeypatch.context() as patch:
        patch.setattr(governance_routes, "record", fail)
        assert (await cash(client, a, "5000.00")).status_code == 500
    assert (await client.get(f"/api/v1/trips/{t['id']}/cash-advances")).json()["items"][0][
        "outstanding"
    ] == "5000.00"
    assert await admin_db.scalar(text("SELECT count(*) FROM cash_advance_settlement_entries")) == 0
    assert (await cash(client, a, "5000.00")).status_code == 200
    assert (await approve(client, t)).status_code == 200
    me = (await client.get("/api/v1/me")).json()
    async with Session() as db:
        await set_context(db, me["user"]["id"], me["organization"]["id"])
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text("UPDATE trip_financial_review_events SET status='APPROVED'"))
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text("DELETE FROM trip_financial_review_events"))
    # A new source record invalidates even when it is not yet reviewed.
    await revenue(client, t, "1.00")
    assert (await financial(client, t))["status"] == "PROVISIONAL"
    assert (await approve(client, t)).status_code == 409
    for body in (
        dict(expected_event_id=None, records_confirmed=False),
        dict(expected_event_id=None, records_confirmed=True, status="APPROVED"),
        dict(expected_event_id=None, records_confirmed=True, reviewed_by=me["user"]["id"]),
    ):
        assert (
            await post(client, f"/trips/{t['id']}/financial-review/approve", body)
        ).status_code == 422
    assert (
        await post(client, f"/cash-advances/{a['id']}/void", dict(reason="  "))
    ).status_code == 422


@pytest.mark.asyncio
async def test_foreign_expense_and_restricted_override(client, admin_db):
    t, ids, _, _ = await fixture(client)
    a = await issue(client, t)
    me = (await client.get("/api/v1/me")).json()
    await login(client, "other-owner@example.com")
    from .test_master_data import fleet
    from .test_trips import create_trip

    other = await create_trip(client, await fleet(client))
    other_a = await issue(client, other)
    assert (await allocate(client, other_a, ids[0])).status_code == 404
    assert (
        await post(client, f"/trips/{other['id']}/cash-advances", dict(source_expense_id=ids[0]))
    ).status_code == 404
    assert (
        await post(
            client,
            f"/trips/{t['id']}/financial-review/approve",
            dict(expected_event_id=None, records_confirmed=True),
        )
    ).status_code == 404
    # Direct tenant references and forged aggregate values fail at PostgreSQL as well.
    identity = (await client.get("/api/v1/me")).json()
    async with Session() as db:
        await set_context(db, identity["user"]["id"], identity["organization"]["id"])
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(
                    text(
                        "INSERT INTO cash_advance_settlement_entries(id,organization_id,trip_id,cash_advance_id,entry_type,amount,reason,created_by) VALUES(:id,:org,:trip,:a,'CASH_RETURNED',1,:reason,:actor)"
                    ),
                    dict(
                        id=uuid.uuid4(),
                        org=uuid.UUID(identity["organization"]["id"]),
                        trip=uuid.UUID(other["id"]),
                        a=uuid.UUID(a["id"]),
                        reason=REASON,
                        actor=uuid.UUID(identity["user"]["id"]),
                    ),
                )
    await login(client)
    await admin_db.execute(
        text(
            "UPDATE organization_memberships SET permissions_json='{"
            + '"deny":["financial_review.approve","cash_advance.settle"]'
            + "}'::jsonb WHERE user_id=:u"
        ),
        dict(u=uuid.UUID(me["user"]["id"])),
    )
    await admin_db.commit()
    assert (await cash(client, a, "1.00")).status_code == 403
    assert (
        await post(
            client,
            f"/trips/{t['id']}/financial-review/approve",
            dict(expected_event_id=None, records_confirmed=True),
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_first_approval_stale_token_and_database_overreturn(client, admin_db):
    t, _, _, _ = await fixture(client)
    s = await state(client, t)
    a = await issue(client, t, "1.00")
    assert (await cash(client, a, "1.00")).status_code == 200
    stale = await post(
        client,
        f"/trips/{t['id']}/financial-review/approve",
        dict(expected_event_id=s["latest_event_id"], records_confirmed=True),
    )
    assert stale.status_code == 409
    me = (await client.get("/api/v1/me")).json()
    async with Session() as db:
        await set_context(db, me["user"]["id"], me["organization"]["id"])
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(
                    text(
                        "INSERT INTO cash_advance_settlement_entries(id,organization_id,trip_id,cash_advance_id,entry_type,amount,reason,created_by) VALUES(:id,:org,:trip,:a,'CASH_RETURNED',1,:reason,:actor)"
                    ),
                    dict(
                        id=uuid.uuid4(),
                        org=uuid.UUID(me["organization"]["id"]),
                        trip=uuid.UUID(t["id"]),
                        a=uuid.UUID(a["id"]),
                        reason=REASON,
                        actor=uuid.UUID(me["user"]["id"]),
                    ),
                )
    assert (await approve(client, t)).status_code == 200
    flags = (
        await admin_db.execute(
            text(
                "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname IN ('cash_advances','cash_advance_settlement_entries','trip_financial_review_events')"
            )
        )
    ).all()
    assert len(flags) == 3 and all(all(row) for row in flags)
