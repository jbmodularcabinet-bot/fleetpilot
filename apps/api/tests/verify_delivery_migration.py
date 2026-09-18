"""Run after the owner golden fixture and Batch 5 downgrade/reapply in the isolated DB."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from fleetpilot.config import get_settings


async def verify():
    settings = get_settings()
    if settings.environment != "test" or not settings.database_url.endswith("/fleetpilot_test"):
        raise RuntimeError("Migration verification requires isolated test database")
    engine = create_async_engine(settings.migration_database_url)
    async with engine.connect() as db:
        completed = (
            await db.execute(
                text(
                    "SELECT current_status,pod_required FROM trips WHERE current_status='COMPLETED'"
                )
            )
        ).all()
        assert completed and all(
            status == "COMPLETED" and required is False for status, required in completed
        )
        assert await db.scalar(text("SELECT count(*) FROM proof_of_delivery")) == 0
        assert (
            await db.scalar(
                text("SELECT count(*) FROM trip_milestones WHERE milestone_type='COMPLETED'")
            )
            > 0
        )
        print(
            "Migration legacy preservation: completed trips/history retained; no fabricated POD; legacy policy explicit."
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(verify())
