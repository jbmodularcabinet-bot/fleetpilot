"""Governance assertions for the disposable HTTPS database/object recovery drill."""

from .test_profitability import post, revenue, review


async def create(client, trip, data):
    await review(client, await revenue(client, trip, "20000.00"))
    for identifier in data["expenses"]:
        result = await post(client, f"/expenses/{identifier}/legacy-review", {"confirmed": True})
        assert result.status_code == 200, result.text
    result = await post(client, f"/trips/{trip['id']}/cash-advances", {"amount": "5000.00"})
    assert result.status_code == 200, result.text
    advance = result.json()["result"]["advance"]["id"]
    result = await post(client, f"/cash-advances/{advance}/cash-return",
                        {"amount": "5000.00", "reason": "Unused advance fully returned."})
    assert result.status_code == 200, result.text
    snapshot = (await client.get(f"/api/v1/trips/{trip['id']}/financial-review")).json()
    result = await post(client, f"/trips/{trip['id']}/financial-review/approve",
                        {"expected_event_id": snapshot["latest_event_id"], "records_confirmed": True})
    assert result.status_code == 200, result.text
    return {"advance": advance}


async def verify(client, state):
    trip = state["trip"]
    snapshot = (await client.get(f"/api/v1/trips/{trip}/financial-review")).json()
    assert snapshot["status"] == "APPROVED" and not snapshot["blockers"]
    financial = snapshot["financials"]
    assert financial["status"] == "FINAL"
    assert financial["direct_cost"]["effective_total"] == "3450.00"
    assert financial["contribution_amount"] == "16550.00"
    advance = (await client.get(f"/api/v1/trips/{trip}/cash-advances")).json()["items"][0]
    assert advance["id"] == state["governance"]["advance"]
    assert advance["outstanding"] == "0.00" and advance["status"] == "SETTLED"
    assert len(advance["history"]) == 1
    for identifier in state["expenses"]:
        original = (await client.get(f"/api/v1/expenses/{identifier}")).json()
        assert original["status"] == "SUBMITTED"
