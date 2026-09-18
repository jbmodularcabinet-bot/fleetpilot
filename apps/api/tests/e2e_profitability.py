"""Populate only the isolated synthetic E2E database through existing domain APIs."""

import asyncio
import json

from httpx import ASGITransport, AsyncClient

from fleetpilot.config import get_settings
from fleetpilot.main import app

from .test_profitability import fixture


async def main():
    settings = get_settings()
    if settings.environment != "test" or not settings.database_url.endswith("/fleetpilot_test"):
        raise RuntimeError("Isolated E2E database required")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": "http://localhost:3000"},
    ) as client:
        trip, ids, _, fleet = await fixture(client)
        print(json.dumps({"trip": trip, "expenses": ids, "vehicle": fleet["vehicles"]["id"]}))


if __name__ == "__main__":
    asyncio.run(main())
