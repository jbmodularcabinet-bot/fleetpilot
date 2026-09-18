from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from fleetpilot.config import Settings
from fleetpilot.permissions import ALL_PERMISSIONS, Role, resolve_permissions
from fleetpilot.schemas import (
    MembershipCreate,
    MembershipUpdate,
    OrganizationCreate,
    OrganizationUpdate,
)
from fleetpilot.tenancy import TenantContext

VALID = {"name": "Test Logistics", "timezone": "Asia/Manila", "currency": "PHP", "country": "PH"}


@pytest.mark.parametrize("role", list(Role))
def test_roles_are_parsed(role):
    assert MembershipUpdate(role=role.value, active=True).role == role
    assert "organization.read" in resolve_permissions(role)


def test_unknown_role_denies_all():
    assert resolve_permissions("ROOT") == frozenset()
    with pytest.raises(ValidationError):
        MembershipUpdate(role="ROOT", active=True)


def test_permission_boundaries():
    assert "users.manage" in resolve_permissions("OWNER")
    assert "users.manage" not in resolve_permissions("MANAGER")
    assert "owner_dashboard.view" not in resolve_permissions("DRIVER")
    assert "driver_app.view" in resolve_permissions("DRIVER")
    assert "driver_app.view" not in resolve_permissions("ADMIN")
    assert resolve_permissions("DRIVER", {"grant": list(ALL_PERMISSIONS)}) == resolve_permissions(
        "DRIVER"
    )
    assert "users.manage" not in resolve_permissions("OWNER", {"deny": ["users.manage"]})


def test_tenant_context_denies_unknown_capability():
    ctx = TenantContext(
        SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), resolve_permissions("DRIVER")
    )
    ctx.require("driver_app.view")
    with pytest.raises(HTTPException) as exc:
        ctx.require("users.manage")
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "key,value",
    [
        ("name", " "),
        ("timezone", "Mars/Olympus"),
        ("timezone", "../etc"),
        ("currency", "ZZZ"),
        ("currency", "php"),
        ("country", "XX"),
        ("country", "PHL"),
    ],
)
def test_invalid_organization_fields(key, value):
    with pytest.raises(ValidationError):
        OrganizationUpdate(**{**VALID, key: value})


def test_organization_validation_and_not_hardcoded_currency():
    assert (
        OrganizationUpdate(
            **{**VALID, "currency": "USD", "timezone": "America/New_York", "country": "US"}
        ).currency
        == "USD"
    )
    assert OrganizationCreate(**VALID, slug="demo-logistics").slug == "demo-logistics"
    with pytest.raises(ValidationError):
        OrganizationCreate(**VALID, slug="INVALID /slug")
    with pytest.raises(ValidationError):
        OrganizationUpdate(**VALID, organization_id="forged")


def test_membership_validation():
    assert MembershipCreate(email="user@example.com", role="DRIVER").role == Role.DRIVER
    with pytest.raises(ValidationError):
        MembershipCreate(email="not-an-email", role="DRIVER")
    with pytest.raises(ValidationError):
        MembershipUpdate(role="DRIVER", active=True, permissions_json={"grant": ["users.manage"]})


def test_production_environment_requires_https_and_secure_cookie():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://app:synthetic@localhost/db",
            web_origin="http://fleetpilot.example.com",
            _env_file=None,
        )
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://app:synthetic@localhost/db",
        web_origin="https://fleetpilot.example.com",
        _env_file=None,
    )
    assert settings.cookie_secure
