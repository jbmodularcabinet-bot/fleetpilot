import asyncio
import uuid

import pytest
from sqlalchemy import text

from .conftest import login
from .delivery_helpers import image_bytes
from .test_expenses import cost, submit
from .test_master_data import DATA, create
from .test_sync import body, send, setup
from .test_trips import create_trip, finish

pytestmark = pytest.mark.asyncio


async def test_trusted_odometer_survives_driver_reassignment_without_history_leak(client, admin_db):
    trip, identity, fleet = await setup(client)
    baseline = await admin_db.scalar(
        text("SELECT odometer FROM vehicles WHERE id=:id"), {"id": fleet["vehicles"]["id"]}
    )
    result = (
        await submit(
            client,
            trip,
            cost("FUEL", amount=None, liters="52.35", price_per_liter="61.75", odometer="52000"),
        )
    ).json()["result"]
    identifier = result["expense"]["id"]
    await client.post("/api/v1/auth/logout")
    await login(client)
    reviewed = await client.post(
        f"/api/v1/expenses/{identifier}/review",
        json={"expected_version": result["trip_version"]},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert reviewed.status_code == 200, reviewed.text
    pedro = uuid.uuid4()
    await admin_db.execute(
        text(
            "INSERT INTO users(id,name,email,hashed_password,is_active,is_verified,is_superuser,status) SELECT :id,'Pedro','pedro-odometer@example.com',hashed_password,true,true,false,'ACTIVE' FROM users WHERE id=:juan"
        ),
        {"id": pedro, "juan": identity["user"]["id"]},
    )
    await admin_db.execute(
        text(
            "INSERT INTO organization_memberships(id,organization_id,user_id,role,active) VALUES(:id,:org,:user,'DRIVER',true)"
        ),
        {"id": uuid.uuid4(), "org": identity["organization"]["id"], "user": pedro},
    )
    await admin_db.commit()
    driver = await create(
        client,
        "drivers",
        {
            **DATA["drivers"],
            "employee_number": "PEDRO-ODO",
            "license_number": None,
            "user_id": str(pedro),
            "first_name": "Pedro",
            "last_name": "Reyes",
        },
    )
    assigned = await client.post(
        f"/api/v1/trips/{trip['id']}/assign",
        json={
            "expected_version": reviewed.json()["result"]["trip_version"],
            "driver_id": driver["id"],
            "vehicle_id": fleet["vehicles"]["id"],
        },
    )
    assert assigned.status_code == 200, assigned.text
    await client.post("/api/v1/auth/logout")
    await login(client, "pedro-odometer@example.com")
    assert (await client.get(f"/api/v1/expenses/{identifier}")).status_code == 404
    assert (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()["total"] == 0
    r = await submit(
        client,
        assigned.json(),
        cost("FUEL", amount=None, liters="1", price_per_liter="60", odometer="51500"),
    )
    assert r.status_code == 409, r.text
    assert (
        await admin_db.scalar(
            text("SELECT odometer FROM vehicles WHERE id=:id"), {"id": fleet["vehicles"]["id"]}
        )
        == baseline
    )
    assert (
        await admin_db.scalar(
            text("SELECT reviewed_fuel_odometer FROM vehicles WHERE id=:id"),
            {"id": fleet["vehicles"]["id"]},
        )
        == 52000
    )


@pytest.mark.parametrize(
    "field", ["organization_id", "driver_id", "vehicle_id", "trip_id", "status"]
)
async def test_queue_claims_are_never_authority(client, field):
    trip, _, _ = await setup(client)
    r = await submit(
        client, trip, cost(**{field: "REVIEWED" if field == "status" else str(uuid.uuid4())})
    )
    assert r.status_code == 422, r.text


async def test_exact_repeated_sum_large_amount_and_pagination(client):
    trip, _, _ = await setup(client)
    for amount in ["0.01"] * 10 + ["1.10", "10000000.00"]:
        r = await submit(client, trip, cost(amount=amount))
        assert r.status_code == 200, r.text
        trip["version"] = r.json()["result"]["trip_version"]
    page = (await client.get(f"/api/v1/trips/{trip['id']}/expenses?limit=1&offset=1")).json()
    assert len(page["items"]) == 1 and page["total"] == 12
    assert page["submitted_total"] == "10000001.20"


async def test_linked_other_driver_with_own_active_trip_denied(client, admin_db):
    trip, identity, fleet = await setup(client)
    created = (
        await submit(client, trip, cost("FUEL", amount=None, liters="1", price_per_liter="60"))
    ).json()["result"]
    identifier = created["expense"]["id"]
    r = await client.post(
        f"/api/v1/expenses/{identifier}/evidence",
        params={"filename": "receipt.png", "expected_version": created["trip_version"]},
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, r.text
    evidence = r.json()["result"]["evidence_id"]
    pedro = uuid.uuid4()
    await admin_db.execute(
        text(
            "INSERT INTO users(id,name,email,hashed_password,is_active,is_verified,is_superuser,status) SELECT :id,'Pedro','pedro-linked@example.com',hashed_password,true,true,false,'ACTIVE' FROM users WHERE id=:juan"
        ),
        {"id": pedro, "juan": identity["user"]["id"]},
    )
    await admin_db.execute(
        text(
            "INSERT INTO organization_memberships(id,organization_id,user_id,role,active) VALUES(:id,:org,:user,'DRIVER',true)"
        ),
        {"id": uuid.uuid4(), "org": identity["organization"]["id"], "user": pedro},
    )
    await admin_db.commit()
    await client.post("/api/v1/auth/logout")
    await login(client)
    driver = await create(
        client,
        "drivers",
        {
            **DATA["drivers"],
            "employee_number": "PEDRO-2",
            "license_number": None,
            "user_id": str(pedro),
            "first_name": "Pedro",
            "last_name": "Reyes",
        },
    )
    vehicle = await create(
        client,
        "vehicles",
        {**DATA["vehicles"], "unit_number": "TRK-002", "plate_number": "PED-222"},
    )
    own = await finish(
        client,
        await create_trip(client, {**fleet, "drivers": driver, "vehicles": vehicle}),
        stop="dispatch",
    )
    await client.post("/api/v1/auth/logout")
    await login(client, "pedro-linked@example.com")
    assert (await client.get(f"/api/v1/driver/trips/{own['id']}")).status_code == 200
    for path in (
        f"/expenses/{identifier}",
        f"/expense-evidence/{evidence}",
        f"/trips/{trip['id']}/expenses",
    ):
        assert (await client.get("/api/v1" + path)).status_code == 404
    assert (await send(client, trip["id"], "expense", body(99, cost()))).status_code == 404
    assert (await submit(client, own, cost())).status_code == 200


async def test_review_race_correction_golden_and_permission_replay(client, admin_db):
    trip, _, _ = await setup(client)
    result = (await submit(client, trip, cost(amount="300.00"))).json()["result"]
    identifier = result["expense"]["id"]
    trip["version"] = result["trip_version"]
    await client.post("/api/v1/auth/logout")
    await login(client)
    responses = await asyncio.gather(
        *(
            client.post(
                f"/api/v1/expenses/{identifier}/review",
                json={"expected_version": trip["version"]},
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            for _ in range(2)
        )
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    trip["version"] = next(
        r.json()["result"]["trip_version"] for r in responses if r.status_code == 200
    )
    data = {
        **cost(amount="350.00"),
        "expected_version": trip["version"],
        "reason": "Receipt amount verified.",
    }
    key = str(uuid.uuid4())
    path = f"/api/v1/expenses/{identifier}/correct"
    r = await client.post(path, json=data, headers={"Idempotency-Key": key})
    assert r.status_code == 200, r.text
    assert [v["amount"] for v in r.json()["result"]["expense"]["revisions"]] == ["300.00", "350.00"]
    assert (await client.post(path, json=data, headers={"Idempotency-Key": key})).json()[
        "outcome"
    ] == "ALREADY_APPLIED"
    assert (
        await client.post(
            path, json={**data, "reason": "Changed"}, headers={"Idempotency-Key": key}
        )
    ).status_code == 409
    me = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text(
            'UPDATE organization_memberships SET permissions_json=\'{"deny":["expenses.correct"]}\'::jsonb WHERE id=:id'
        ),
        {"id": me["membership"]["id"]},
    )
    await admin_db.commit()
    assert (await client.post(path, json=data, headers={"Idempotency-Key": key})).status_code == 403


async def test_receipt_supersession_retains_original_and_failed_store_is_atomic(
    client, admin_db, monkeypatch
):
    from fleetpilot import expense_routes

    trip, _, _ = await setup(client)
    result = (await submit(client, trip, cost())).json()["result"]
    identifier = result["expense"]["id"]

    async def upload(version, **params):
        return await client.post(
            f"/api/v1/expenses/{identifier}/evidence",
            params={"filename": "receipt.png", "expected_version": version, **params},
            content=image_bytes(),
            headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
        )

    first = await upload(result["trip_version"])
    assert first.status_code == 200, first.text
    old = first.json()["result"]
    second = await upload(old["trip_version"], supersedes_id=old["evidence_id"])
    assert second.status_code == 200, second.text
    detail = (await client.get(f"/api/v1/expenses/{identifier}")).json()
    assert [r["status"] for r in detail["evidence"]] == ["SUPERSEDED", "ACTIVE"]
    assert (await client.get("/api/v1/expense-evidence/" + old["evidence_id"])).status_code == 200
    store = expense_routes.storage()

    def fail(*args):
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(type(store), "put", fail)
    r = await upload(second.json()["result"]["trip_version"])
    assert r.status_code == 500
    assert await admin_db.scalar(text("SELECT count(*) FROM expense_evidence")) == 2
    assert (
        await admin_db.scalar(
            text("SELECT count(*) FROM audit_logs WHERE action='expense_evidence.uploaded'")
        )
        == 2
    )
