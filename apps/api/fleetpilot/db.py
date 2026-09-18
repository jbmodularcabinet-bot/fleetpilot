from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.concurrency import run_in_threadpool

from .config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with Session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            for store, key in session.info.get("uncommitted_evidence", []):
                try:
                    await run_in_threadpool(store.discard_uncommitted, key)
                except Exception:
                    from .hardening import emit

                    emit("storage.cleanup_failed")
            raise


async def set_context(db: AsyncSession, user_id: str, organization_id: str = "") -> None:
    # Transaction-local settings cannot leak when connections return to the pool.
    await db.execute(
        text(
            "SELECT set_config('app.user_id', :user, true), set_config('app.organization_id', :org, true)"
        ),
        {"user": user_id, "org": organization_id},
    )
