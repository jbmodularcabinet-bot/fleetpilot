import hashlib
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context
from fleetpilot.main import app, login_windows, settings
from fleetpilot.models import AccessToken, AuditLog, Membership, Organization, User
from fleetpilot.seed import DEMO_ORG, OTHER_ORG

from .conftest import login

pytestmark = pytest.mark.integration


async def test_health_and_startup(client):
    async with app.router.lifespan_context(app):
        assert (await client.get("/health")).json() == {"status": "ok"}
        assert (await client.get("/ready")).status_code == 200


async def test_login_session_persistence_logout_and_hash(client, admin_db):
    assert (await client.get("/api/v1/me")).status_code == 401
    response = await login(client)
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    token = client.cookies.get("fp_session")
    record = await admin_db.scalar(select(AccessToken))
    assert record.token == hashlib.sha256(token.encode()).hexdigest()
    for _ in range(2):
        me = await client.get("/api/v1/me")
        assert me.status_code == 200, me.text
        assert me.json()["membership"]["role"] == "OWNER"
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    client.cookies.set("fp_session", token)
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_bad_credentials_and_csrf(client):
    response = await client.post(
        "/api/v1/auth/login", data={"username": "carlo@example.com", "password": "wrong"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Email or password is incorrect."
    assert (
        await client.post("/api/v1/auth/login", headers={"Origin": "https://evil.invalid"})
    ).status_code == 403
    client.headers.pop("Origin")
    assert (await client.post("/api/v1/auth/logout")).status_code == 403


async def test_login_rate_limit(client):
    login_windows["127.0.0.1"] = (__import__("time").monotonic(), settings.login_limit)
    assert (await client.post("/api/v1/auth/login")).status_code == 429


async def test_expired_and_forged_session(client, admin_db):
    await login(client)
    await admin_db.execute(text("UPDATE auth_sessions SET created_at = now() - interval '2 days'"))
    await admin_db.commit()
    assert (await client.get("/api/v1/me")).status_code == 401
    client.cookies.clear()
    client.cookies.set("fp_session", "forged")
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_owner_reads_own_not_other_organization(client):
    await login(client)
    assert (await client.get(f"/api/v1/organizations/{DEMO_ORG}")).status_code == 200
    assert (await client.get(f"/api/v1/organizations/{OTHER_ORG}")).status_code == 404
    result = (await client.get("/api/v1/me")).json()
    assert [org["id"] for org in result["organizations"]] == [str(DEMO_ORG)]
    client.cookies.set("fp_organization", str(OTHER_ORG))
    assert (await client.get("/api/v1/me")).status_code == 403


async def test_org_switch_checks_membership(client, admin_db):
    await login(client)
    assert (
        await client.post(
            "/api/v1/organization-selection", json={"organization_id": str(OTHER_ORG)}
        )
    ).status_code == 403
    user = await admin_db.scalar(select(User).where(User.email == "carlo@example.com"))
    admin_db.add(Membership(organization_id=OTHER_ORG, user_id=user.id, role="MANAGER"))
    await admin_db.commit()
    assert (
        await client.post(
            "/api/v1/organization-selection", json={"organization_id": str(OTHER_ORG)}
        )
    ).status_code == 200
    result = (await client.get("/api/v1/me")).json()
    assert result["organization"]["id"] == str(OTHER_ORG)
    assert result["membership"]["role"] == "MANAGER"


async def test_organization_save_persists_and_audits(client, admin_db):
    await login(client)
    payload = {
        "name": "Updated Demo",
        "legal_name": "Demo Legal",
        "currency": "USD",
        "country": "US",
        "timezone": "America/New_York",
    }
    response = await client.patch(f"/api/v1/organizations/{DEMO_ORG}", json=payload)
    assert response.status_code == 200, response.text
    assert (await client.get(f"/api/v1/organizations/{DEMO_ORG}")).json()["name"] == "Updated Demo"
    log = await admin_db.scalar(select(AuditLog).where(AuditLog.action == "organization.updated"))
    assert log.before_json["name"] == "Demo Logistics Corp."
    assert log.after_json["name"] == "Updated Demo"
    assert (
        await client.patch(f"/api/v1/organizations/{OTHER_ORG}", json=payload)
    ).status_code == 404
    assert (
        await client.patch(f"/api/v1/organizations/{DEMO_ORG}", json={**payload, "currency": "ZZZ"})
    ).status_code == 422


async def test_cannot_edit_other_tenant_membership(client, admin_db):
    await login(client)
    member = await admin_db.scalar(
        select(Membership).where(Membership.organization_id == OTHER_ORG)
    )
    response = await client.patch(
        f"/api/v1/memberships/{member.id}", json={"role": "DRIVER", "active": False}
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "role,can_read,can_manage,dashboard,driver",
    [
        ("OWNER", True, True, True, False),
        ("ADMIN", True, True, True, False),
        ("MANAGER", True, False, True, False),
        ("DRIVER", False, False, False, True),
        ("DISPATCHER", False, False, False, False),
        ("ACCOUNTING", False, False, False, False),
        ("MAINTENANCE", False, False, False, False),
    ],
)
async def test_all_role_boundaries(client, admin_db, role, can_read, can_manage, dashboard, driver):
    user = await admin_db.scalar(select(User).where(User.email == "carlo@example.com"))
    member = await admin_db.scalar(select(Membership).where(Membership.user_id == user.id))
    member.role = role
    await admin_db.commit()
    await login(client)
    assert (await client.get("/api/v1/memberships")).status_code == (200 if can_read else 403)
    response = await client.post(
        "/api/v1/memberships", json={"email": "other-owner@example.com", "role": "DRIVER"}
    )
    assert response.status_code == (201 if can_manage else 403), response.text
    permissions = (await client.get("/api/v1/me")).json()["permissions"]
    assert ("owner_dashboard.view" in permissions) == dashboard
    assert ("driver_app.view" in permissions) == driver


async def test_role_change_disable_and_audit(client, admin_db):
    await login(client)
    members = (await client.get("/api/v1/memberships")).json()
    driver = next(m for m in members if m["role"] == "DRIVER")
    assert (
        await client.patch(
            f"/api/v1/memberships/{driver['id']}", json={"role": "DISPATCHER", "active": True}
        )
    ).status_code == 200
    assert (
        await client.patch(
            f"/api/v1/memberships/{driver['id']}", json={"role": "DISPATCHER", "active": False}
        )
    ).status_code == 200
    actions = [log.action for log in (await admin_db.scalars(select(AuditLog))).all()]
    assert "membership.role_changed" in actions
    assert "membership.disabled" in actions
    await login(client, "juan@example.com")
    assert (await client.get("/api/v1/me")).status_code == 403


async def test_membership_unique_self_change_and_admin_escalation(client, admin_db):
    await login(client)
    assert (
        await client.post(
            "/api/v1/memberships", json={"email": "juan@example.com", "role": "DRIVER"}
        )
    ).status_code == 409
    me = (await client.get("/api/v1/me")).json()
    assert (
        await client.patch(
            f"/api/v1/memberships/{me['membership']['id']}", json={"role": "DRIVER", "active": True}
        )
    ).status_code == 409
    member = await admin_db.get(Membership, uuid.UUID(me["membership"]["id"]))
    member.role = "ADMIN"
    await admin_db.commit()
    assert (
        await client.post(
            "/api/v1/memberships", json={"email": "other-owner@example.com", "role": "OWNER"}
        )
    ).status_code == 403


async def test_inactive_user_and_suspended_organization(client, admin_db):
    await login(client)
    org = await admin_db.get(Organization, DEMO_ORG)
    org.status = "SUSPENDED"
    await admin_db.commit()
    assert (await client.get("/api/v1/me")).status_code == 403
    org.status = "ACTIVE"
    user = await admin_db.scalar(select(User).where(User.email == "carlo@example.com"))
    user.is_active = False
    await admin_db.commit()
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_rls_direct_queries_and_pool_context(client, admin_db):
    user = await admin_db.scalar(select(User).where(User.email == "carlo@example.com"))
    async with Session() as db:
        assert not (await db.scalars(select(Organization))).all()
        await set_context(db, str(user.id), str(DEMO_ORG))
        assert [o.id for o in (await db.scalars(select(Organization))).all()] == [DEMO_ORG]
        assert all(
            m.organization_id == DEMO_ORG for m in (await db.scalars(select(Membership))).all()
        )
        assert all(
            a.organization_id == DEMO_ORG for a in (await db.scalars(select(AuditLog))).all()
        )
        await db.commit()
        assert not (await db.scalars(select(Organization))).all()
    async with Session() as db:
        await set_context(db, str(user.id), str(DEMO_ORG))
        db.add(Membership(organization_id=OTHER_ORG, user_id=user.id, role="DRIVER"))
        with pytest.raises(DBAPIError):
            await db.flush()


async def test_audit_is_immutable_and_no_secrets(client, admin_db):
    await login(client)
    logs = await client.get("/api/v1/audit-logs")
    assert logs.status_code == 200
    assert "hashed_password" not in logs.text and "fp_session" not in logs.text
    with pytest.raises(DBAPIError):
        await admin_db.execute(text("UPDATE audit_logs SET action='tampered'"))
    await admin_db.rollback()
