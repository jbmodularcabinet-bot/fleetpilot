"""Synthetic Batch 14 browser data; all financial and lifecycle writes use APIs."""

import asyncio
import contextlib
import io
import json

from httpx import ASGITransport, AsyncClient

from fleetpilot.main import app
from fleetpilot.trip_lifecycle import ACTIONS

from .conftest import login
from .e2e_setup import provision
from .test_expenses import cost
from .test_master_data import fleet
from .test_profitability import post, revenue, review
from .test_trips import act, create_trip


async def main():
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        await provision("settlement", True)
    identity = json.loads(capture.getvalue())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": "http://localhost:3000"},
    ) as c:
        await login(c, identity["email"])
        data = await fleet(c)
        trips = []
        for partial in (False, True):
            t = await create_trip(c, data)
            t = await act(c, t, "dispatch")
            ids = []
            for fields in (
                [cost(amount="3000.00")]
                if partial
                else [
                    cost("FUEL", amount=None, liters="50", price_per_liter="50"),
                    cost(amount="700.00"),
                ]
            ):
                r = await post(
                    c, f"/trips/{t['id']}/expenses", dict(expected_version=t["version"], **fields)
                )
                assert r.status_code == 200, r.text
                t["version"] = r.json()["result"]["trip_version"]
                e = r.json()["result"]["expense"]["id"]
                ids.append(e)
                r = await post(c, f"/expenses/{e}/review", dict(expected_version=t["version"]))
                assert r.status_code == 200, r.text
                t["version"] = r.json()["result"]["trip_version"]
            for action in list(ACTIONS)[1:]:
                t = await act(c, t, action)
            r = await c.post(
                f"/api/v1/trips/{t['id']}/complete",
                json=dict(expected_version=t["version"], closeout_reviewed=True),
            )
            assert r.status_code == 200, r.text
            t = r.json()
            await review(c, await revenue(c, t, "20000.00"))
            trips.append(dict(trip=t, expenses=ids))
    print(json.dumps(dict(**identity, trips=trips)))


if __name__ == "__main__":
    asyncio.run(main())
