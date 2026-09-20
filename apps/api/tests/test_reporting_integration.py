"""Database-backed reporting checks against the existing disposable test database only."""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event, text

from fleetpilot.db import Session, engine, set_context
from fleetpilot.reporting_contract import REPORTS, REQUIRED_ACCESS
from fleetpilot.trip_models import Trip

from .conftest import login
from .test_adjustments import adjustment, apply, reverse
from .test_expenses import cost, submit
from .test_profitability import fixture, post, revenue, review

pytestmark = pytest.mark.asyncio


async def prepared(client, close=False):
    trip, expense_ids, driver, masters = await fixture(client, close=close)
    await review(client, await revenue(client, trip))
    day = (
        datetime.fromisoformat(trip["scheduled_pickup_at"])
        .astimezone(ZoneInfo("Asia/Manila"))
        .date()
        .isoformat()
    )
    return trip, expense_ids, masters, {"date_from": day, "date_to": day}


async def report(client, params, name="executive-contribution", code=200):
    r = await client.get("/api/v1/reports/" + name, params=params)
    assert r.status_code == code, r.text
    return r


async def test_six_reports_reconcile_and_exports_are_complete(client):
    trip, _, _, params = await prepared(client)
    fingerprints = set()
    for name in REPORTS:
        r = await report(client, params, name)
        body = r.json()
        s = body["summary"]
        assert (
            s["revenue"],
            s["direct_cost"],
            s["contribution"],
            s["weighted_margin_percent"],
        ) == ("25000.00", "10300.00", "14700.00", "58.80")
        assert s["trip_count"] == 1 and s["provisional_count"] == 1 and s["final_count"] == 0
        assert body["scope"]["date_basis"] == "Scheduled pickup date"
        assert r.headers["cache-control"] == "no-store"
        fingerprints.add(body["scope"]["fingerprint"])
        export = await report(client, {**params, "format": "csv"}, name)
        assert (
            "text/csv" in export.headers["content-type"]
            and "attachment" in export.headers["content-disposition"]
        )
        assert "not net profit" in export.text and "Scheduled pickup date" in export.text
        printed = await report(client, {**params, "format": "print"}, name)
        assert "Print / Save as PDF" in printed.text
    assert len(fingerprints) == 1
    summary = (await client.get("/api/v1/intelligence/overview", params=params)).json()
    assert summary["summary"]["contribution"] == "14700.00"
    assert summary["priority_findings"]
    assert (await report(client, {**params, "trip_id": trip["id"]}, "trip-contribution")).json()[
        "total"
    ] == 1


async def test_effective_correction_void_reversal_and_material_history(client):
    trip, ids, _, params = await prepared(client, close=True)
    policy = {
        "low_margin_percent": "15.00",
        "direct_cost_pressure_percent": "70.00",
        "cost_concentration_percent": "50.00",
        "material_change_php": "250.00",
    }
    assert (await client.patch("/api/v1/reports/policy", json=policy)).status_code == 200
    adjusted = await apply(client, trip, adjustment(ids[1], value="1500.00"))
    assert adjusted.status_code == 200, adjusted.text
    r = (await report(client, params, "financial-exceptions")).json()
    assert r["summary"]["direct_cost"] == "10800.00"
    assert r["summary"]["contribution"] == "14200.00"
    assert any(f["rule_id"] == "MATERIAL_FINANCIAL_CHANGE" for f in r["items"])
    aid = adjusted.json()["result"]["adjustment_id"]
    assert (await reverse(client, aid, 1)).status_code == 200
    assert (await report(client, params)).json()["summary"]["direct_cost"] == "10300.00"
    assert (await client.get("/api/v1/expenses/" + ids[1])).json()["current"]["amount"] == "1000.00"


async def test_capture_issuance_and_partial_settlement_are_not_double_counted(client):
    trip, ids, _, params = await prepared(client)
    await login(client, "juan@example.com")
    captured = await submit(client, trip, cost("DRIVER_CASH_ADVANCE", amount="5000.00"))
    assert captured.status_code == 200, captured.text
    capture_id = captured.json()["result"]["expense"]["id"]
    await login(client)
    r = (await report(client, params, "cash-advances")).json()
    assert (
        r["advance_summary"]["captured_amount"],
        r["advance_summary"]["issued"],
        r["advance_summary"]["outstanding"],
    ) == ("5000.00", "0.00", "0.00")
    assert r["advance_summary"]["unreconciled_capture_count"] == 1
    issued = await post(
        client,
        f"/trips/{trip['id']}/cash-advances",
        {"source_expense_id": capture_id, "purpose": "Synthetic reconciliation test"},
    )
    assert issued.status_code == 200, issued.text
    aid = issued.json()["result"]["advance"]["id"]
    applied = await post(
        client,
        f"/cash-advances/{aid}/apply-expense",
        {"expense_id": ids[1], "reason": "Synthetic reviewed toll allocation"},
    )
    assert applied.status_code == 200, applied.text
    returned = await post(
        client,
        f"/cash-advances/{aid}/cash-return",
        {"amount": "1000.00", "reason": "Synthetic driver cash returned"},
    )
    assert returned.status_code == 200, returned.text
    r = (await report(client, params, "cash-advances")).json()
    assert (
        r["advance_summary"]["captured_amount"],
        r["advance_summary"]["issued"],
        r["advance_summary"]["applied"],
        r["advance_summary"]["returned"],
        r["advance_summary"]["outstanding"],
    ) == ("5000.00", "5000.00", "1000.00", "1000.00", "3000.00")
    assert r["summary"]["direct_cost"] == "10300.00" and r["summary"]["contribution"] == "14700.00"
    assert r["total"] == 2 and {a["record_kind"] for a in r["items"]} == {"CAPTURE", "ISSUANCE"}


@pytest.mark.parametrize("role", ["OWNER", "ADMIN", "MANAGER", "ACCOUNTING"])
async def test_report_access_actual_roles(client, admin_db, role):
    _, _, _, params = await prepared(client)
    me = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text("UPDATE organization_memberships SET role=:role WHERE user_id=:u"),
        {"role": role, "u": uuid.UUID(me["user"]["id"])},
    )
    await admin_db.commit()
    r = (await report(client, params)).json()
    assert r["summary"]["trip_count"] == 1 and r["summary"]["contribution"] == "14700.00"
    assert r["history_available"] == (role in {"OWNER", "ADMIN"})


@pytest.mark.parametrize("denied", REQUIRED_ACCESS)
async def test_denied_financial_visibility_denies_summary_and_exports(client, admin_db, denied):
    _, _, _, params = await prepared(client)
    me = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text(
            "UPDATE organization_memberships SET permissions_json=CAST(:p AS jsonb) WHERE user_id=:u"
        ),
        {"p": json.dumps({"deny": [denied]}), "u": uuid.UUID(me["user"]["id"])},
    )
    await admin_db.commit()
    for format in ("json", "csv", "print"):
        r = await report(client, {**params, "format": format}, code=403)
        assert "summary" not in r.json()


@pytest.mark.parametrize("role", ["DRIVER", "DISPATCHER", "MAINTENANCE"])
async def test_unauthorized_roles_direct_urls(client, admin_db, role):
    await login(client)
    me = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text("UPDATE organization_memberships SET role=:role WHERE user_id=:u"),
        {"role": role, "u": uuid.UUID(me["user"]["id"])},
    )
    await admin_db.commit()
    for name in REPORTS:
        await report(client, {}, name, 403)
    assert (await client.get("/api/v1/intelligence/overview")).status_code == 403


async def test_cross_tenant_filters_and_runtime_rls(client):
    trip, _, masters, params = await prepared(client)
    await login(client, "other-owner@example.com")
    me = (await client.get("/api/v1/me")).json()
    assert (await report(client, params)).json()["summary"]["trip_count"] == 0
    for filter, value in (
        ("trip_id", trip["id"]),
        ("customer_id", masters["customers"]["id"]),
        ("vehicle_id", masters["vehicles"]["id"]),
    ):
        await report(client, {**params, filter: value}, code=404)
    async with Session() as db:
        await set_context(db, me["user"]["id"], me["organization"]["id"])
        assert not await db.scalar(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")
        )
        for table in (
            "trips",
            "trip_revenue",
            "trip_expenses",
            "cash_advances",
            "closed_trip_adjustments",
        ):
            assert await db.scalar(text("SELECT count(*) FROM " + table)) == 0
    await client.post("/api/v1/auth/logout")
    await report(client, params, code=401)


async def test_policy_bounds_owner_authorization_and_audit(client, admin_db):
    await login(client)
    me = (await client.get("/api/v1/me")).json()
    policy = {
        "low_margin_percent": "18.00",
        "direct_cost_pressure_percent": "72.00",
        "cost_concentration_percent": "55.00",
        "material_change_php": "1500.00",
    }
    response = await client.patch("/api/v1/reports/policy", json=policy)
    assert response.status_code == 200, response.text
    assert (await client.get("/api/v1/reports/policy")).json()["policy"] == policy
    assert (
        await admin_db.scalar(
            text("SELECT count(*) FROM audit_logs WHERE action='reporting_policy.updated'")
        )
        == 1
    )
    assert (
        await client.patch(
            "/api/v1/reports/policy", json={**policy, "low_margin_percent": "100.01"}
        )
    ).status_code == 422
    await admin_db.execute(
        text("UPDATE organization_memberships SET role='MANAGER' WHERE user_id=:u"),
        {"u": uuid.UUID(me["user"]["id"])},
    )
    await admin_db.commit()
    assert (await client.patch("/api/v1/reports/policy", json=policy)).status_code == 403


async def test_synthetic_selection_and_final_filters(client, admin_db):
    trip, _, _, params = await prepared(client)
    me = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text(
            "UPDATE organizations SET settings_json=settings_json || CAST(:s AS jsonb) WHERE id=:id"
        ),
        {
            "s": json.dumps({"reporting_synthetic_trip_ids": [trip["id"]]}),
            "id": uuid.UUID(me["organization"]["id"]),
        },
    )
    await admin_db.commit()
    assert (await report(client, params)).json()["summary"]["trip_count"] == 0
    synthetic = (await report(client, {**params, "dataset": "synthetic"})).json()
    assert synthetic["summary"]["trip_count"] == 1 and synthetic["scope"]["synthetic"]
    assert (
        await report(client, {**params, "dataset": "synthetic", "financial_status": "FINAL"})
    ).json()["summary"]["trip_count"] == 0
    assert (
        "SYNTHETIC VALIDATION DATA"
        in (await report(client, {**params, "dataset": "synthetic", "format": "csv"})).text
    )


async def test_report_is_coherent_during_concurrent_financial_write(client, monkeypatch):
    from fleetpilot import reporting_service

    trip, ids, _, params = await prepared(client, close=True)
    entered, release = asyncio.Event(), asyncio.Event()
    original = reporting_service.calculate_many

    async def barrier(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(reporting_service, "calculate_many", barrier)
    reading = asyncio.create_task(report(client, params))
    await asyncio.wait_for(entered.wait(), 5)
    writing = asyncio.create_task(apply(client, trip, adjustment(ids[1], value="1500.00")))
    await asyncio.sleep(0.15)
    assert not writing.done()
    release.set()
    result = (await reading).json()
    assert (
        result["summary"]["direct_cost"] == "10300.00"
        and result["summary"]["contribution"] == "14700.00"
    )
    assert (await writing).status_code == 200
    monkeypatch.setattr(reporting_service, "calculate_many", original)
    updated = (await report(client, params)).json()
    assert (
        updated["summary"]["direct_cost"] == "10800.00"
        and updated["summary"]["contribution"] == "14200.00"
    )
    assert updated["scope"]["fingerprint"] != result["scope"]["fingerprint"]


async def test_more_than_one_page_aggregates_complete_cohort(client, admin_db):
    trip, _, masters, params = await prepared(client)
    me = (await client.get("/api/v1/me")).json()
    await set_context(admin_db, me["user"]["id"], me["organization"]["id"])
    admin_db.add_all(
        [
            Trip(
                id=uuid.uuid4(),
                organization_id=uuid.UUID(me["organization"]["id"]),
                trip_number=f"SYNTHETIC-PAGE-{number}",
                number_sequence=1000 + number,
                customer_id=uuid.UUID(masters["customers"]["id"]),
                pickup_name="TEST",
                pickup_address="TEST",
                delivery_name="TEST",
                delivery_address="TEST",
                scheduled_pickup_at=datetime.fromisoformat(trip["scheduled_pickup_at"])
                - timedelta(hours=4)
                + timedelta(minutes=number),
                current_status="SCHEDULED",
                current_milestone="SCHEDULED",
                version=1,
                created_by=uuid.UUID(me["user"]["id"]),
                updated_by=uuid.UUID(me["user"]["id"]),
            )
            for number in range(1, 121)
        ]
    )
    await admin_db.commit()
    statements = []

    def count(*args):
        statements.append(args[2])

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    try:
        result = (await report(client, {**params, "limit": 20}, "trip-contribution")).json()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count)
    assert (
        result["summary"]["trip_count"] == 121
        and result["total"] == 121
        and len(result["items"]) == 20
    )
    assert (
        result["summary"]["revenue"] == "25000.00"
        and result["summary"]["insufficient_data_count"] == 120
    )
    assert all(t["revenue"] == "0.00" for t in result["items"])
    assert len(statements) <= 25, len(statements)
    assert (await report(client, {**params, "offset": 120}, "trip-contribution")).json()["items"][
        0
    ]["id"] == trip["id"]
    exported = await report(client, {**params, "format": "csv"}, "trip-contribution")
    assert "SYNTHETIC-PAGE-120" in exported.text and trip["trip_number"] in exported.text
