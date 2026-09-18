"""Provision a fresh synthetic organization and owner for a browser golden workflow."""

import asyncio
import json
import os
import sys
import uuid

from fastapi_users.password import PasswordHelper
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fleetpilot.config import get_settings
from fleetpilot.models import AuditLog, Membership, Organization, User


async def provision(label, with_driver=False):
    settings = get_settings()
    if settings.environment != "test" or not settings.database_url.endswith("/fleetpilot_test"):
        raise RuntimeError("Browser provisioning is restricted to the isolated test database")
    engine = create_async_engine(settings.migration_database_url)
    suffix = uuid.uuid4().hex
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        org = Organization(
            name=f"Golden Organization {label}",
            slug=f"golden-{label.lower()}-{suffix}",
            timezone="Asia/Manila",
            currency="PHP",
            country="PH",
            settings_json={"synthetic": True},
        )
        owner = User(
            name=f"Golden Owner {label}",
            email=f"golden-{suffix}@example.com",
            hashed_password=PasswordHelper().hash(os.environ["DEMO_PASSWORD"]),
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        db.add_all([org, owner])
        await db.flush()
        db.add(Membership(organization_id=org.id, user_id=owner.id, role="OWNER"))
        driver = None
        if with_driver:
            driver = User(
                name="Juan Dela Cruz",
                email=f"driver-{suffix}@example.com",
                hashed_password=PasswordHelper().hash(os.environ["DEMO_PASSWORD"]),
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
            db.add(driver)
            await db.flush()
            db.add(Membership(organization_id=org.id, user_id=driver.id, role="DRIVER"))
        db.add(
            AuditLog(
                organization_id=org.id,
                actor_user_id=owner.id,
                action="organization.created",
                entity_type="organization",
                entity_id=org.id,
                after_json={"synthetic": True},
            )
        )
        await db.commit()
        print(
            json.dumps(
                {
                    "email": owner.email,
                    "organization_id": str(org.id),
                    **(
                        {"driver_email": driver.email, "driver_user_id": str(driver.id)}
                        if driver
                        else {}
                    ),
                }
            )
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(provision(sys.argv[1], "--driver" in sys.argv[2:]))
