"""Bounded HTTP load against the disposable local HTTPS restore drill only."""

import asyncio
import json
import math
import os
import time
from pathlib import Path

import httpx


async def main():
    state_file = Path(os.environ["DRILL_STATE"])
    if os.environ.get("DRILL_BATCH9") != "1" or "fleetpilot_restore_" not in os.environ.get(
        "DATABASE_URL", ""
    ):
        raise RuntimeError("Load test requires disposable local restore database")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    paths = [
        "/trips",
        "/dispatch",
        f"/trips/{state['trip']}",
        f"/trips/{state['trip']}/expenses",
        f"/vehicles/{state['vehicle']}/fuel-history",
    ]
    extended = os.environ.get("DRILL_BATCH12") == "1"
    if extended:
        paths += [
            "/maintenance/work-orders",
            f"/vehicles/{state['vehicle']}",
            "/maintenance-evidence/" + state["maintenance"]["evidence"][0]["id"],
        ]
    concurrency, iterations = (5, 12) if extended else (4, 5)
    timings = {p: [] for p in ["login", *paths]}
    errors = {p: 0 for p in timings}
    timeouts = {p: 0 for p in timings}

    async def worker():
        async with httpx.AsyncClient(
            base_url="https://127.0.0.1:8446",
            verify=False,
            headers={"Origin": "https://localhost:8446"},
            timeout=30,
        ) as c:
            for _ in range(iterations):
                for path in ["login", *paths]:
                    start = time.perf_counter()
                    try:
                        if path == "login":
                            r = await c.post(
                                "/api/v1/auth/login",
                                data={
                                    "username": "carlo@example.com",
                                    "password": os.environ["DEMO_PASSWORD"],
                                },
                            )
                            errors[path] += r.status_code != 204
                        else:
                            r = await c.get("/api/v1" + path)
                            errors[path] += r.status_code != 200
                    except httpx.TimeoutException:
                        errors[path] += 1
                        timeouts[path] += 1
                    except httpx.HTTPError:
                        errors[path] += 1
                    finally:
                        timings[path].append((time.perf_counter() - start) * 1000)

    await asyncio.gather(*(worker() for _ in range(concurrency)))

    def stats(values, failures, timed_out):
        v = sorted(values)
        return {
            "requests": len(v),
            "p50_ms": round(v[math.ceil(len(v) * 0.5) - 1], 2),
            "p95_ms": round(v[math.ceil(len(v) * 0.95) - 1], 2),
            "p99_ms": round(v[math.ceil(len(v) * 0.99) - 1], 2),
            "timeouts": timed_out,
            "timeout_rate": timed_out / len(v),
            "errors": failures,
            "error_rate": failures / len(v),
        }

    report = {
        "environment": "LOCAL disposable restored PostgreSQL / HTTPS API / private loopback S3",
        "concurrency": concurrency,
        "total": stats(
            [x for v in timings.values() for x in v], sum(errors.values()), sum(timeouts.values())
        ),
        "routes": {p: stats(v, errors[p], timeouts[p]) for p, v in timings.items()},
        "production_capacity": "UNVERIFIED",
    }
    (state_file.parent / "load-result.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    assert sum(errors.values()) == 0, report
    print(json.dumps(report))


if __name__ == "__main__":
    asyncio.run(main())
