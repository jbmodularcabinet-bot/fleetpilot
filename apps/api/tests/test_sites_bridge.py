import hashlib
import time
import uuid

import jwt
import pytest
from sqlalchemy import text

from fleetpilot.config import get_settings

pytestmark = pytest.mark.asyncio
ISSUER = "https://pilot.chatgpt.site"
AUDIENCE = "https://parent.example"
SECRET = "bridge-test-only-" + "x" * 48
ORG = "11111111-1111-4111-8111-111111111111"


def assertion(**changes):
    now = int(time.time())
    payload = dict(
        iss=ISSUER,
        aud=AUDIENCE,
        sub="site-owner",
        iat=now,
        nbf=now,
        exp=now + 30,
        jti=uuid.uuid4().hex,
        scope="parent:me",
    )
    payload.update(changes)
    return jwt.encode(payload, SECRET, algorithm="HS256")


async def configure(admin_db, monkeypatch, email="carlo@example.com"):
    for key, value in dict(
        sites_bridge_secret=SECRET,
        sites_bridge_issuer=ISSUER,
        sites_bridge_audience=AUDIENCE,
        sites_bridge_organization_id=ORG,
    ).items():
        monkeypatch.setitem(get_settings().__dict__, key, value)
    provider = "sites:" + hashlib.sha256((ISSUER + "\nsite-owner").encode()).hexdigest()
    await admin_db.execute(
        text("UPDATE users SET auth_provider_id=:p WHERE email=:e"), {"p": provider, "e": email}
    )
    await admin_db.commit()


async def test_bridge_resolves_existing_principal(client, admin_db, monkeypatch):
    await configure(admin_db, monkeypatch)
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer " + assertion()})
    assert r.status_code == 200, r.text
    assert r.json()["organization"]["id"] == ORG
    assert r.json()["membership"]["role"] == "OWNER"
    assert not r.headers.get("set-cookie")


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "unmapped"},
        {"iss": "https://evil.example"},
        {"aud": "wrong"},
        {"exp": 1},
        {"exp": int(time.time()) + 3600},
        {"scope": "finance:write"},
        {"nbf": int(time.time()) + 300},
    ],
)
async def test_bad_assertions_denied(client, admin_db, monkeypatch, claims):
    await configure(admin_db, monkeypatch)
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer " + assertion(**claims)})
    assert r.status_code == 401


async def test_bridge_cannot_access_other_routes(client, admin_db, monkeypatch):
    await configure(admin_db, monkeypatch)
    r = await client.get("/api/v1/memberships", headers={"Authorization": "Bearer " + assertion()})
    assert r.status_code == 401


@pytest.mark.parametrize("email", ["juan@example.com", "other-owner@example.com"])
async def test_wrong_role_or_tenant_denied(client, admin_db, monkeypatch, email):
    await configure(admin_db, monkeypatch, email)
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer " + assertion()})
    assert r.status_code == 403


async def test_cross_tenant_cookie_denied(client, admin_db, monkeypatch):
    await configure(admin_db, monkeypatch)
    client.cookies.set("fp_organization", "22222222-2222-4222-8222-222222222222")
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer " + assertion()})
    assert r.status_code == 403
