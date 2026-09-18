import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fleetpilot.config import get_settings
from fleetpilot.main import app, login_windows
from fleetpilot.rate_limits import other_windows
from fleetpilot.seed import seed


@pytest_asyncio.fixture
async def admin_db():
    settings = get_settings()
    if settings.environment != "test" or not settings.database_url.endswith("/fleetpilot_test"):
        raise RuntimeError("Integration tests require isolated fleetpilot_test database")
    engine = create_async_engine(settings.migration_database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        yield db
    await engine.dispose()


@pytest_asyncio.fixture
async def client(admin_db):
    # Only the explicitly isolated test database may be reset.
    await admin_db.execute(
        text(
            "TRUNCATE auth_sessions, audit_logs, organization_memberships, organizations, users CASCADE"
        )
    )
    await admin_db.commit()
    await seed()
    login_windows.clear()
    other_windows.clear()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": "http://localhost:3000"},
    ) as client:
        yield client


async def login(client, email="carlo@example.com"):
    response = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": os.environ["DEMO_PASSWORD"]}
    )
    assert response.status_code == 204, response.text
    return response
