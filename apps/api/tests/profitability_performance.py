"""Bounded LOCAL ASGI/PostgreSQL check after the browser golden; never production."""

import asyncio
import json
import time
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from fleetpilot.config import get_settings
from fleetpilot.db import engine
from fleetpilot.main import app

from .conftest import login


async def main():
    settings = get_settings()
    if settings.environment != "test" or not settings.database_url.endswith("/fleetpilot_test"):
        raise RuntimeError("Isolated local test database required")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": "http://localhost:3000"},
    ) as client:
        await login(client)
        initial = (await client.get("/api/v1/profitability/trips")).json()
        assert initial["total"] >= 1, "Run the profitability browser golden first"
        identifier = initial["items"][0]["trip_id"]
        trip = (await client.get("/api/v1/trips/" + identifier)).json()
        for _ in range(max(0, 20 - initial["total"])):
            response = await client.post(
                "/api/v1/trips",
                json=dict(
                    customer_id=trip["customer_id"],
                    pickup_name="Performance origin",
                    pickup_address="Synthetic road",
                    delivery_name="Performance destination",
                    delivery_address="Synthetic site",
                    scheduled_pickup_at="2030-01-10T00:00:00Z",
                ),
            )
            assert response.status_code == 201, response.text
        count = [0]

        def statement(*args):
            count[0] += 1

        event.listen(engine.sync_engine, "before_cursor_execute", statement)
        report = {}
        try:
            for name, path in [
                ("single", "/trips/" + identifier + "/financials"),
                ("list", "/profitability/trips?limit=20"),
                (
                    "date_filtered",
                    "/profitability/trips?limit=20&date_from=2030-01-01T00:00:00Z&date_to=2030-12-31T23:59:59Z",
                ),
            ]:
                times = []
                queries = []
                for _ in range(100):
                    count[0] = 0
                    start = time.perf_counter()
                    response = await client.get("/api/v1" + path)
                    assert response.status_code == 200, response.text
                    times.append((time.perf_counter() - start) * 1000)
                    queries.append(count[0])
                times.sort()
                report[name] = {
                    "requests": 100,
                    "p50_ms": round(times[49], 2),
                    "p95_ms": round(times[94], 2),
                    "max_sql_statements": max(queries),
                    "errors": 0,
                }
            # Pagination changes rows, not the number of financial aggregation queries.
            counts = []
            for limit in (1, 20):
                count[0] = 0
                response = await client.get("/api/v1/profitability/trips?limit=" + str(limit))
                assert response.status_code == 200
                assert len(response.json()["items"]) == limit
                counts.append(count[0])
            assert counts[0] == counts[1], counts
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", statement)
        output = {
            "environment": "LOCAL in-process ASGI and real PostgreSQL, synthetic 20-trip tenant; not network or production capacity",
            "requests": 302,
            "concurrency": 1,
            "routes": report,
            "list_query_counts_1_and_20": counts,
        }
        Path("../../.runtime/batch13-performance.json").write_text(
            json.dumps(output, indent=2), encoding="utf-8"
        )
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
