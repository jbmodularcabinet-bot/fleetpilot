"""Automatic sample-data entry is explicit, read-only and tenant bounded."""

import json
import uuid

import pytest

from fleetpilot.config import get_settings

from .conftest import login
from .test_reporting_integration import prepared, report

pytestmark = pytest.mark.asyncio


async def test_business_tenant_has_no_automatic_sample_defaults(client):
    await login(client)
    response = await client.get("/api/v1/reports/demo-context")
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["filters"] == {}
    assert response.headers["cache-control"] == "no-store"


async def test_demo_context_uses_real_sample_dates_without_financial_mutation(client, monkeypatch):
    trip, _, _, period = await prepared(client)
    me = (await client.get("/api/v1/me")).json()
    monkeypatch.setattr(
        get_settings(),
        "reporting_synthetic_trips_json",
        json.dumps({me["organization"]["id"]: [trip["id"]]}),
    )
    before = (await client.get(f"/api/v1/trips/{trip['id']}/financials")).json()
    response = await client.get("/api/v1/reports/demo-context")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["organization_id"] == me["organization"]["id"]
    assert data["available"] is True and data["trip_count"] == 1
    assert data["filters"] == {**period, "dataset": "synthetic"}
    assert (await report(client, data["filters"])).json()["summary"]["revenue"] == "25000.00"
    assert (await report(client, {**period, "dataset": "business"})).json()["summary"][
        "trip_count"
    ] == 0
    after = (await client.get(f"/api/v1/trips/{trip['id']}/financials")).json()
    before.pop("calculated_at")
    after.pop("calculated_at")
    assert before == after
    assert (await client.get(f"/api/v1/trips/{trip['id']}")).json()["scheduled_pickup_at"] == trip[
        "scheduled_pickup_at"
    ]


async def test_demo_context_does_not_follow_another_tenant_manifest(client, monkeypatch):
    trip, _, _, _ = await prepared(client)
    owner = (await client.get("/api/v1/me")).json()
    monkeypatch.setattr(
        get_settings(),
        "reporting_synthetic_trips_json",
        json.dumps({owner["organization"]["id"]: [trip["id"]]}),
    )
    await login(client, "other-owner@example.com")
    other = (await client.get("/api/v1/me")).json()
    response = await client.get("/api/v1/reports/demo-context")
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["organization_id"] == other["organization"]["id"]
    assert trip["id"] not in response.text
    monkeypatch.setattr(
        get_settings(),
        "reporting_synthetic_trips_json",
        json.dumps({other["organization"]["id"]: [trip["id"]]}),
    )
    assert (await client.get("/api/v1/reports/demo-context")).status_code == 409


async def test_missing_configured_samples_are_an_error_not_zero_demo(client, monkeypatch):
    await login(client)
    me = (await client.get("/api/v1/me")).json()
    monkeypatch.setattr(
        get_settings(),
        "reporting_synthetic_trips_json",
        json.dumps({me["organization"]["id"]: [str(uuid.uuid4())]}),
    )
    response = await client.get("/api/v1/reports/demo-context")
    assert response.status_code == 409
    assert "recreated or substituted" in response.text


async def test_demo_context_does_not_authorize_driver_or_anonymous(client):
    assert (await client.get("/api/v1/reports/demo-context")).status_code == 401
    await login(client, "juan@example.com")
    assert (await client.get("/api/v1/reports/demo-context")).status_code == 403


async def test_production_does_not_select_demo_by_default(client, monkeypatch):
    await login(client)
    monkeypatch.setattr(get_settings(), "environment", "production")
    response = await client.get("/api/v1/reports/demo-context")
    assert response.status_code == 200
    assert response.json()["available"] is False and response.json()["filters"] == {}
