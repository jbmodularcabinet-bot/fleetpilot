import uuid

import pytest
from sqlalchemy import text

from fleetpilot.client_demo_access import (
    CLIENT_DEMO_ACCESS_PROFILE,
    CLIENT_DEMO_ALLOWED_PERMISSIONS,
    CLIENT_DEMO_ROLE,
    client_demo_overrides,
)
from fleetpilot.permissions import ROLE_PERMISSIONS

from .test_profitability import post
from .test_reporting_integration import prepared, report

pytestmark = pytest.mark.asyncio


async def test_client_demo_profile_is_restrictive_only():
    base = ROLE_PERMISSIONS[CLIENT_DEMO_ROLE]
    overrides = client_demo_overrides()
    assert CLIENT_DEMO_ALLOWED_PERMISSIONS < base
    assert set(overrides["deny"]) == base - CLIENT_DEMO_ALLOWED_PERMISSIONS
    assert overrides["profile"] == CLIENT_DEMO_ACCESS_PROFILE


async def restricted_client_demo(client, admin_db):
    trip, expense_ids, _, params = await prepared(client)
    me = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text(
            "UPDATE organization_memberships "
            "SET role=:role,permissions_json=CAST(:permissions AS jsonb) "
            "WHERE user_id=:user"
        ),
        {
            "role": CLIENT_DEMO_ROLE.value,
            "permissions": __import__("json").dumps(client_demo_overrides()),
            "user": uuid.UUID(me["user"]["id"]),
        },
    )
    await admin_db.commit()
    return trip, expense_ids, params


async def test_client_demo_reads_reports_and_financial_drilldown(client, admin_db):
    trip, _, params = await restricted_client_demo(client, admin_db)
    identity = (await client.get("/api/v1/me")).json()
    assert identity["membership"]["access_profile"] == CLIENT_DEMO_ACCESS_PROFILE
    assert set(identity["permissions"]) == CLIENT_DEMO_ALLOWED_PERMISSIONS

    assert (await client.get("/api/v1/intelligence/overview", params=params)).status_code == 200
    for name in (
        "executive-contribution",
        "trip-contribution",
        "customer-contribution",
        "direct-costs",
        "financial-exceptions",
        "cash-advances",
    ):
        assert (await report(client, params, name)).status_code == 200
    csv = await report(client, {**params, "format": "csv"}, "trip-contribution")
    assert "text/csv" in csv.headers["content-type"]
    assert (await client.get(f"/api/v1/trips/{trip['id']}")).status_code == 200
    assert (await client.get(f"/api/v1/trips/{trip['id']}/financials")).status_code == 200
    assert (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).status_code == 200


async def test_client_demo_mutations_and_admin_surfaces_are_denied(client, admin_db):
    trip, expense_ids, _ = await restricted_client_demo(client, admin_db)
    identity = (await client.get("/api/v1/me")).json()
    org = identity["organization"]

    denied = [
        await client.patch(
            f"/api/v1/organizations/{org['id']}",
            json={
                "name": org["name"],
                "legal_name": org["legal_name"],
                "timezone": org["timezone"],
                "currency": org["currency"],
                "country": org["country"],
            },
        ),
        await client.get("/api/v1/memberships"),
        await client.get("/api/v1/audit-logs"),
        await post(
            client,
            f"/trips/{trip['id']}/revenue",
            {"revenue_type": "SURCHARGE", "amount": "1.00"},
        ),
        await post(
            client,
            f"/expenses/{expense_ids[0]}/review",
            {"expected_version": trip["version"]},
        ),
        await post(
            client,
            f"/trips/{trip['id']}/cash-advances",
            {"amount": "100.00", "purpose": "Denied demo mutation"},
        ),
    ]
    assert [response.status_code for response in denied] == [403] * len(denied)


async def test_client_demo_cross_tenant_and_policy_changes_are_denied(client, admin_db):
    _, _, params = await restricted_client_demo(client, admin_db)
    foreign = str(uuid.uuid4())
    assert (
        await client.get(
            "/api/v1/reports/trip-contribution",
            params={**params, "customer_id": foreign},
        )
    ).status_code == 404
    assert (
        await client.patch(
            "/api/v1/reports/policy",
            json={
                "low_margin_percent": "16.00",
                "direct_cost_pressure_percent": "70.00",
                "cost_concentration_percent": "50.00",
                "material_change_php": "1000.00",
            },
        )
    ).status_code == 403
