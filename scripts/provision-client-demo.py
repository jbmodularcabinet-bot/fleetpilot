"""Provision one isolated, read-only client-demo account. No owner credentials are touched."""

import argparse
import asyncio
import json
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from fastapi_users.password import PasswordHelper
from fleetpilot.client_demo_access import (
    CLIENT_DEMO_ACCESS_PROFILE,
    CLIENT_DEMO_EMAIL,
    CLIENT_DEMO_ROLE,
    client_demo_overrides,
)
from fleetpilot.models import AuditLog, Membership, Organization, User
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

NAME = "FleetPilot Client Demo"
ORG_SLUG = "demo-logistics"


def load_env(path: Path) -> dict[str, str]:
    values = {k: v for k, v in dotenv_values(path).items() if v is not None}
    if values.get("ENVIRONMENT", "development") == "production":
        raise RuntimeError("Client-demo provisioning is disabled in production")
    url = urlparse(values.get("MIGRATION_DATABASE_URL", ""))
    if (
        url.scheme not in {"postgresql+asyncpg", "postgresql"}
        or url.hostname != "127.0.0.1"
        or url.path != "/fleetpilot"
    ):
        raise RuntimeError("Expected the local FleetPilot development database")
    return values


def write_credential(path: Path, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError("Credential file already exists; refusing silent overwrite")
    path.write_text(
        json.dumps({"email": CLIENT_DEMO_EMAIL, "password": password}, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


async def provision(env: dict[str, str], credential_file: Path) -> dict[str, object]:
    engine = create_async_engine(env["MIGRATION_DATABASE_URL"])
    password_helper = PasswordHelper()
    overrides = client_demo_overrides()
    created_user = False
    created_membership = False
    password: str | None = None
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        database = await db.scalar(text("SELECT current_database()"))
        if database != "fleetpilot":
            raise RuntimeError("Unexpected database; refusing client-demo provisioning")
        org = await db.scalar(select(Organization).where(Organization.slug == ORG_SLUG))
        if org is None or org.status != "ACTIVE":
            raise RuntimeError("Demo Logistics organization is not active")
        user = await db.scalar(select(User).where(User.email == CLIENT_DEMO_EMAIL))
        if user is None:
            password = secrets.token_urlsafe(24)
            user = User(
                email=CLIENT_DEMO_EMAIL,
                name=NAME,
                hashed_password=password_helper.hash(password),
                is_active=True,
                is_verified=True,
                is_superuser=False,
                status="ACTIVE",
            )
            db.add(user)
            await db.flush()
            created_user = True
        elif not user.is_active or user.status != "ACTIVE":
            raise RuntimeError(
                "Existing client-demo account is inactive; review manually"
            )
        member = await db.scalar(
            select(Membership).where(
                Membership.organization_id == org.id,
                Membership.user_id == user.id,
            )
        )
        if member is None:
            member = Membership(
                organization_id=org.id,
                user_id=user.id,
                role=CLIENT_DEMO_ROLE.value,
                permissions_json=overrides,
                active=True,
            )
            db.add(member)
            await db.flush()
            created_membership = True
        else:
            if (
                member.role != CLIENT_DEMO_ROLE.value
                or member.permissions_json != overrides
                or not member.active
            ):
                raise RuntimeError(
                    "Existing client-demo membership differs from the locked read-only profile"
                )
        if created_user:
            db.add(
                AuditLog(
                    organization_id=org.id,
                    actor_user_id=None,
                    action="client_demo.account_provisioned",
                    entity_type="user",
                    entity_id=user.id,
                    after_json={
                        "email": CLIENT_DEMO_EMAIL,
                        "profile": CLIENT_DEMO_ACCESS_PROFILE,
                    },
                )
            )
        if created_membership:
            db.add(
                AuditLog(
                    organization_id=org.id,
                    actor_user_id=None,
                    action="client_demo.membership_provisioned",
                    entity_type="membership",
                    entity_id=member.id,
                    after_json={
                        "role": member.role,
                        "profile": CLIENT_DEMO_ACCESS_PROFILE,
                        "active": True,
                    },
                )
            )
        await db.commit()
        if created_user:
            assert password is not None
            write_credential(credential_file, password)
        elif not credential_file.exists():
            raise RuntimeError(
                "Account exists but local credential file is absent; refusing password reset"
            )
        result = {
            "email": CLIENT_DEMO_EMAIL,
            "profile": CLIENT_DEMO_ACCESS_PROFILE,
            "role": member.role,
            "created_user": created_user,
            "created_membership": created_membership,
            "credential_file": str(credential_file),
            "owner_credentials_changed": False,
        }
    await engine.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(provision(load_env(args.env_file), args.credential_file))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
