"""Real HTTPS API workflow used by the disposable backup/restore drill."""

import asyncio
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import httpx

from .conftest import login
from .delivery_helpers import review_delivery
from .test_delivery import successful
from .test_master_data import DATA, fleet
from .test_trips import act, create_trip


async def verify(client, state):
    auth = await login(client)
    if os.environ.get("DRILL_BATCH12") == "1":
        cookie = auth.headers.get("set-cookie", "").lower()
        assert all(flag in cookie for flag in ["secure", "httponly", "samesite=lax"])
        response = await client.get("/health")
        assert all(
            name in response.headers
            for name in [
                "content-security-policy",
                "x-content-type-options",
                "referrer-policy",
                "permissions-policy",
                "strict-transport-security",
            ]
        )
        assert "frame-ancestors" in response.headers["content-security-policy"]
    trip = (await client.get(f"/api/v1/trips/{state['trip']}")).json()
    assert trip["current_status"] == "COMPLETED"
    assert trip["customer_name"] == "ACME Logistics Client"
    assert trip["driver_name"] == "Juan Dela Cruz" and trip["vehicle_unit"] == "TRK-001"
    history = (await client.get(f"/api/v1/trips/{state['trip']}/delivery-attempts")).json()
    assert history["items"][0]["pod"]["status"] == "REVIEWED"
    events = (await client.get(f"/api/v1/trips/{state['trip']}/milestones")).json()
    assert events[-1]["milestone_type"] == "COMPLETED" and len(events) >= 14
    if "expenses" in state:
        totals = (await client.get(f"/api/v1/trips/{state['trip']}/expenses")).json()
        assert totals["submitted_total"] == "3450.00"
        adjustments = (await client.get(f"/api/v1/trips/{state['trip']}/adjustments")).json()
        assert adjustments["total"] == 1 and adjustments["items"][0]["amount_delta"] == "50.00"
        original = (await client.get(f"/api/v1/expenses/{state['expenses'][1]}")).json()
        assert (
            original["current"]["amount"] == "300.00"
            and original["effective"]["amount"] == "350.00"
        )
        receipt = await client.get("/api/v1/expense-evidence/" + state["receipt"]["id"])
        assert (
            receipt.status_code == 200
            and hashlib.sha256(receipt.content).hexdigest() == state["receipt"]["checksum"]
        )
    timings = {}
    if state.get("governance"):
        from .governance_recovery import verify as verify_governance

        await verify_governance(client, state)
    for path in [
        "/customers",
        "/vehicles",
        "/drivers",
        "/dispatch",
        f"/trips/{state['trip']}",
        f"/pod/{state['pod']}",
    ]:
        start = time.perf_counter()
        assert (await client.get("/api/v1" + path)).status_code == 200
        timings[path.split("/")[1]] = round((time.perf_counter() - start) * 1000, 2)
    for evidence in state["evidence"]:
        start = time.perf_counter()
        response = await client.get("/api/v1/evidence/" + evidence["id"])
        assert response.status_code == 200
        assert hashlib.sha256(response.content).hexdigest() == evidence["checksum"]
        timings["evidence_retrieval_ms"] = round((time.perf_counter() - start) * 1000, 2)
    await client.post("/api/v1/auth/logout")
    for evidence in state["evidence"]:
        assert (await client.get("/api/v1/evidence/" + evidence["id"])).status_code == 401
    await login(client, "other-owner@example.com")
    for evidence in state["evidence"]:
        assert (await client.get("/api/v1/evidence/" + evidence["id"])).status_code == 404
    if "maintenance" in state:
        from .maintenance_recovery import verify as verify_maintenance

        await verify_maintenance(client, state)
    return timings


async def main():
    state_file = Path(os.environ["DRILL_STATE"])
    async with httpx.AsyncClient(
        base_url="https://127.0.0.1:8446",
        verify=False,
        headers={"Origin": "https://localhost:8446"},
        timeout=30,
    ) as client:
        assert (await client.get("/health")).json() == {"status": "ok"}
        assert (await client.get("/ready")).json() == {"status": "ready"}
        if not state_file.exists():
            await login(client, "juan@example.com")
            juan = (await client.get("/api/v1/me")).json()["user"]["id"]
            await client.post("/api/v1/auth/logout")
            await login(client)
            rows = await fleet(client)
            assert (
                await client.patch(
                    f"/api/v1/drivers/{rows['drivers']['id']}",
                    json={**DATA["drivers"], "user_id": juan},
                )
            ).status_code == 200
            trip = await act(client, await create_trip(client, rows), "dispatch")
            assert (await client.get("/api/v1/dispatch")).json()["total"] == 1
            expense_state = {}
            if os.environ.get("DRILL_BATCH9") == "1":
                from .delivery_helpers import image_bytes
                from .test_expenses import cost

                ids = []
                for data in [
                    cost("FUEL", amount=None, liters="50", price_per_liter="60"),
                    cost(amount="300.00"),
                    cost("PARKING", amount="100.00"),
                ]:
                    response = await client.post(
                        f"/api/v1/trips/{trip['id']}/expenses",
                        json={**data, "expected_version": trip["version"]},
                        headers={"Idempotency-Key": str(uuid.uuid4())},
                    )
                    assert response.status_code == 200, response.text
                    result = response.json()["result"]
                    ids.append(result["expense"]["id"])
                    trip["version"] = result["trip_version"]
                response = await client.post(
                    f"/api/v1/expenses/{ids[0]}/evidence",
                    params={"filename": "receipt.png", "expected_version": trip["version"]},
                    content=image_bytes(),
                    headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
                )
                assert response.status_code == 200, response.text
                result = response.json()["result"]
                trip["version"] = result["trip_version"]
                expense_state = {
                    "expenses": ids,
                    "receipt": (await client.get(f"/api/v1/expenses/{ids[0]}")).json()["evidence"][
                        0
                    ],
                    "vehicle": rows["vehicles"]["id"],
                }

            await client.post("/api/v1/auth/logout")
            await login(client, "juan@example.com")
            from fleetpilot.trip_lifecycle import ACTIONS

            for action in list(ACTIONS)[1:]:
                if action == "deliver":
                    break
                trip = await act(client, trip, action, prefix="/api/v1/driver/trips")
            start = time.perf_counter()
            _, photo, signature, result = await successful(client, trip)
            upload_ms = round((time.perf_counter() - start) * 1000, 2)
            await client.post("/api/v1/auth/logout")
            await login(client)
            trip = await review_delivery(client, result["trip"])
            response = await client.post(
                f"/api/v1/trips/{trip['id']}/complete",
                json={"expected_version": trip["version"], "closeout_reviewed": True},
            )
            assert response.status_code == 200
            if expense_state:
                from .test_adjustments import adjustment

                response = await client.post(
                    f"/api/v1/trips/{trip['id']}/adjustments",
                    json=adjustment(expense_state["expenses"][1]),
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                )
                assert response.status_code == 200, response.text
            if os.environ.get("DRILL_BATCH12") == "1":
                from .maintenance_recovery import create as create_maintenance

                expense_state["maintenance"] = await create_maintenance(client, rows, trip)
            if os.environ.get("DRILL_BATCH15") == "1":
                from .governance_recovery import create as create_governance

                expense_state["governance"] = await create_governance(client, trip, expense_state)
            state_file.write_text(
                json.dumps(
                    {
                        **expense_state,
                        "trip": trip["id"],
                        "pod": result["pod"]["id"],
                        "evidence": [photo["evidence"], signature["evidence"]],
                        "upload_and_submit_ms": upload_ms,
                    },
                    indent=2,
                )
            )
        timings = await verify(client, json.loads(state_file.read_text()))
        print(json.dumps({"workflow": "PASS", "single_user_timings_ms": timings}))


if __name__ == "__main__":
    asyncio.run(main())
