"""Reset only the named synthetic E2E database; never reuse application data."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from fleetpilot.config import get_settings
from fleetpilot.seed import seed


async def main():
    settings = get_settings()
    if settings.environment != "test" or not settings.database_url.endswith("/fleetpilot_test"):
        raise RuntimeError("E2E reset requires the isolated fleetpilot_test database")
    engine = create_async_engine(settings.migration_database_url)
    async with engine.begin() as db:
        await db.execute(
            text(
                "TRUNCATE auth_sessions, audit_logs, organization_memberships, organizations, users, request_rate_windows CASCADE"
            )
        )
    await engine.dispose()
    await seed()


if __name__ == "__main__":
    asyncio.run(main())
