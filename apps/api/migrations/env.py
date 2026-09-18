import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from fleetpilot import (
    adjustment_models,  # noqa: F401
    delivery_models,  # noqa: F401
    expense_models,  # noqa: F401
    financial_models,  # noqa: F401
    governance_models,  # noqa: F401
    maintenance_models,  # noqa: F401
    master_models,  # noqa: F401
    trip_models,  # noqa: F401
)
from fleetpilot.config import get_settings
from fleetpilot.models import Base


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    settings = get_settings()
    engine = create_async_engine(settings.migration_database_url or settings.database_url)
    async with engine.connect() as connection:
        await connection.run_sync(run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url, target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
