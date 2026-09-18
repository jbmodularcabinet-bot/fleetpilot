"""Explicit, repeatable synthetic development seed. Never run during application startup."""

import asyncio
import os
import uuid

from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import get_settings
from .models import AuditLog, Membership, Organization, User

DEMO_ORG = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = uuid.UUID("22222222-2222-4222-8222-222222222222")


async def seed():
    settings = get_settings()
    if settings.environment not in {"development", "test"}:
        raise RuntimeError("Synthetic seeding is prohibited in production")
    password = os.environ.get("DEMO_PASSWORD", "")
    if len(password) < 16 or password.startswith("REPLACE"):
        raise RuntimeError("Set a synthetic DEMO_PASSWORD of at least 16 characters")
    engine = create_async_engine(settings.migration_database_url or settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        for org_id, name, slug in [
            (DEMO_ORG, "Demo Logistics Corp.", "demo-logistics"),
            (OTHER_ORG, "Isolation Test Logistics", "isolation-test"),
        ]:
            if not await db.get(Organization, org_id):
                db.add(
                    Organization(
                        id=org_id,
                        name=name,
                        slug=slug,
                        timezone="Asia/Manila",
                        currency="PHP",
                        country="PH",
                        settings_json={"synthetic": True},
                    )
                )
                await db.flush()
                db.add(
                    AuditLog(
                        organization_id=org_id,
                        action="organization.created",
                        entity_type="organization",
                        entity_id=org_id,
                        after_json={"name": name, "synthetic": True},
                    )
                )
        for email, name, role, org_id in [
            ("carlo@example.com", "Carlo Santos", "OWNER", DEMO_ORG),
            ("juan@example.com", "Juan Dela Cruz", "DRIVER", DEMO_ORG),
            ("other-owner@example.com", "Test Owner", "OWNER", OTHER_ORG),
        ]:
            user = await db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(
                    email=email,
                    name=name,
                    hashed_password=PasswordHelper().hash(password),
                    is_active=True,
                    is_verified=True,
                    is_superuser=False,
                )
                db.add(user)
                await db.flush()
            member = await db.scalar(
                select(Membership).where(
                    Membership.user_id == user.id, Membership.organization_id == org_id
                )
            )
            if not member:
                member = Membership(organization_id=org_id, user_id=user.id, role=role)
                db.add(member)
                await db.flush()
                db.add(
                    AuditLog(
                        organization_id=org_id,
                        actor_user_id=user.id,
                        action="membership.created",
                        entity_type="membership",
                        entity_id=member.id,
                        after_json={"role": role, "synthetic": True},
                    )
                )
        await db.commit()
    await engine.dispose()
    print(
        "Synthetic organizations and owner/driver accounts are ready. Existing records were preserved."
    )


if __name__ == "__main__":
    asyncio.run(seed())
