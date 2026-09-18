import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context
from fleetpilot.trip_lifecycle import ACTIONS

from .conftest import login
from .test_adjustments import adjustment, apply
from .test_expenses import cost, submit
from .test_governance import approve, state
from .test_profitability import financial, post, revenue, review
from .test_sync import setup
from .test_trips import act

pytestmark = pytest.mark.asyncio


async def legacy_fixture(client):
    trip, _, _ = await setup(client)
    expense_ids = []
    entries = [
        cost("FUEL", amount=None, liters="40", price_per_liter="100", odometer="12500"),
        cost("TOLL", amount="500.00"),
        cost("PARKING", amount="200.00"),
    ]
    for entry in entries:
        response = await submit(client, trip, entry)
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        expense_ids.append(result["expense"]["id"])
        trip["version"] = result["trip_version"]
    await login(client)
    for action in list(ACTIONS)[1:]:
        trip = await act(client, trip, action)
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/complete",
        json={"expected_version": trip["version"], "closeout_reviewed": True},
    )
    assert response.status_code == 200, response.text
    trip = response.json()
    await review(client, await revenue(client, trip, "20000.00"))
    return trip, expense_ids


async def accept(client, expense_id, key=None):
    return await post(
        client,
        f"/expenses/{expense_id}/legacy-review",
        {"confirmed": True},
        key,
    )


async def test_legacy_golden_review_correction_and_finalization(client, admin_db):
    trip, ids = await legacy_fixture(client)
    review_state = await state(client, trip)
    assert review_state["status"] == "NEEDS_ATTENTION"
    assert review_state["blockers"] == ["Direct expenses await review."]
    assert len(review_state["legacy_expenses"]) == 3
    queue = (await client.get("/api/v1/financial-review/legacy")).json()
    assert queue["total"] == 1 and queue["items"][0]["unreviewed_expenses"] == 3
    assert (await accept(client, ids[0])).status_code == 200
    assert (await accept(client, ids[1])).status_code == 200
    correction = await apply(client, trip, adjustment(ids[2], value="150.00"))
    assert correction.status_code == 200, correction.text
    assert (await accept(client, ids[2])).status_code == 200
    f = await financial(client, trip)
    assert f["direct_cost"]["effective_total"] == "4650.00"
    assert f["contribution_amount"] == "15350.00"
    assert f["contribution_margin_percent"] == "76.75"
    review_state = await state(client, trip)
    assert review_state["status"] == "READY_FOR_REVIEW"
    assert review_state["legacy_expenses"] == []
    assert (await approve(client, trip)).status_code == 200
    assert (await financial(client, trip))["status"] == "FINAL"
    original = (await client.get(f"/api/v1/expenses/{ids[2]}")).json()
    assert original["current"]["amount"] == "200.00"
    assert original["effective"]["amount"] == "150.00"
    actions = set((await admin_db.execute(text("SELECT action FROM audit_logs"))).scalars())
    assert "legacy_expense.reviewed" in actions and "financial_review.approved" in actions


async def test_legacy_void_removes_blocker_without_overwriting_source(client):
    trip, ids = await legacy_fixture(client)
    for identifier in ids[:2]:
        assert (await accept(client, identifier)).status_code == 200
    voided = await apply(
        client,
        trip,
        adjustment(ids[2], kind="VOID_ADJUSTMENT", value=None, reason="Duplicate legacy submission."),
    )
    assert voided.status_code == 200, voided.text
    detail = (await client.get(f"/api/v1/expenses/{ids[2]}")).json()
    assert detail["current"]["amount"] == "200.00"
    assert detail["effective"]["voided"] is True
    assert (await state(client, trip))["legacy_expenses"] == []
    assert (await financial(client, trip))["direct_cost"]["effective_total"] == "4500.00"


async def test_legacy_acceptance_is_idempotent_and_history_append_only(client, admin_db):
    trip, ids = await legacy_fixture(client)
    key = str(uuid.uuid4())
    first = await accept(client, ids[0], key)
    second = await accept(client, ids[0], key)
    assert first.status_code == 200 and second.status_code == 200
    assert {first.json()["outcome"], second.json()["outcome"]} == {"APPLIED", "ALREADY_APPLIED"}
    with pytest.raises(DBAPIError):
        async with admin_db.begin_nested():
            await admin_db.execute(text("UPDATE legacy_expense_review_events SET action='ACCEPTED'"))
    with pytest.raises(DBAPIError):
        async with admin_db.begin_nested():
            await admin_db.execute(text("DELETE FROM legacy_expense_review_events"))


async def test_legacy_rbac_tenant_and_direct_rls(client):
    trip, ids = await legacy_fixture(client)
    await login(client, "juan@example.com")
    assert (await client.get("/api/v1/financial-review/legacy")).status_code == 403
    assert (await accept(client, ids[0])).status_code == 403
    await login(client, "other-owner@example.com")
    assert (await client.get("/api/v1/financial-review/legacy")).json()["total"] == 0
    assert (await accept(client, ids[0])).status_code == 404
    other = (await client.get("/api/v1/me")).json()
    async with Session() as db:
        await set_context(db, other["user"]["id"], other["organization"]["id"])
        assert await db.scalar(text("SELECT count(*) FROM legacy_expense_review_events")) == 0


async def test_outstanding_advance_remains_a_blocker_after_legacy_review(client):
    trip, ids = await legacy_fixture(client)
    for identifier in ids:
        assert (await accept(client, identifier)).status_code == 200
    advance = await post(client, f"/trips/{trip['id']}/cash-advances", {"amount": "1000.00"})
    assert advance.status_code == 200, advance.text
    current = await state(client, trip)
    assert "Cash advance remains outstanding." in current["blockers"]
    assert (await approve(client, trip)).status_code == 409
    assert (await financial(client, trip))["status"] == "PROVISIONAL"
