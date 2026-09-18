import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from fleetpilot import routes
from fleetpilot.models import Organization
from fleetpilot.seed import DEMO_ORG

from .conftest import login

pytestmark = pytest.mark.integration


async def test_audit_failure_rolls_back_organization_change(client, admin_db, monkeypatch):
    await login(client)

    def reject_audit(*args, **kwargs):
        raise IntegrityError("synthetic failure", {}, Exception("audit unavailable"))

    monkeypatch.setattr(routes, "record", reject_audit)
    response = await client.patch(
        f"/api/v1/organizations/{DEMO_ORG}",
        json={
            "name": "Must not persist",
            "legal_name": None,
            "timezone": "Asia/Manila",
            "currency": "PHP",
            "country": "PH",
        },
    )
    assert response.status_code == 409
    org = await admin_db.scalar(select(Organization).where(Organization.id == DEMO_ORG))
    assert org.name == "Demo Logistics Corp."
