"""Explicit operator-only account/organization provisioning; no public signup endpoint."""

import argparse
import asyncio
import getpass

from fastapi_users.password import PasswordHelper
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import get_settings
from .models import AuditLog, Membership, Organization, User
from .schemas import OrganizationCreate


async def provision(args):
    settings = get_settings()
    if not settings.migration_database_url:
        raise RuntimeError("Operator provisioning requires MIGRATION_DATABASE_URL")
    email = str(TypeAdapter(EmailStr).validate_python(args.email)).lower()
    password = getpass.getpass("Initial password (minimum 16 characters): ")
    if len(password) < 16 or len(password) > 128:
        raise ValueError("Password must be 16–128 characters")
    if password != getpass.getpass("Confirm initial password: "):
        raise ValueError("Passwords do not match")
    engine = create_async_engine(settings.migration_database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        if await db.scalar(select(User).where(User.email == email)):
            raise ValueError("Account already exists; provisioning does not reset passwords")
        user = User(
            email=email,
            name=args.name,
            hashed_password=PasswordHelper().hash(password),
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        db.add(user)
        await db.flush()
        if args.organization:
            payload = OrganizationCreate(
                name=args.organization,
                slug=args.slug,
                timezone=args.timezone,
                currency=args.currency,
                country=args.country,
            )
            org = Organization(**payload.model_dump())
            db.add(org)
            await db.flush()
            member = Membership(organization_id=org.id, user_id=user.id, role="OWNER")
            db.add(member)
            await db.flush()
            db.add_all(
                [
                    AuditLog(
                        organization_id=org.id,
                        actor_user_id=user.id,
                        action="organization.created",
                        entity_type="organization",
                        entity_id=org.id,
                        after_json={"name": org.name},
                    ),
                    AuditLog(
                        organization_id=org.id,
                        actor_user_id=user.id,
                        action="membership.created",
                        entity_type="membership",
                        entity_id=member.id,
                        after_json={"role": "OWNER", "active": True},
                    ),
                ]
            )
        await db.commit()
    await engine.dispose()
    print(
        "Account provisioned. No password was logged. Add an organization membership through settings if needed."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--organization")
    parser.add_argument("--slug")
    parser.add_argument("--timezone", default="Asia/Manila")
    parser.add_argument("--currency", default="PHP")
    parser.add_argument("--country", default="PH")
    args = parser.parse_args()
    if args.organization and not args.slug:
        parser.error("--slug is required with --organization")
    asyncio.run(provision(args))
