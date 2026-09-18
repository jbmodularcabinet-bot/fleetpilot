import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context

from .conftest import login
from .delivery_helpers import image_bytes
from .test_sync import body, send, setup

pytestmark = pytest.mark.asyncio


def cost(category="TOLL", **fields):
    return {
        "category": category,
        "amount": "350.00",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }


async def submit(client, trip, fields, key=None):
    return await send(client, trip["id"], "expense", body(trip["version"], fields), key)


async def test_expense_golden_exact_review_correction_void(client, admin_db):
    trip, _, fleet = await setup(client)
    ids = []
    for data in [
        cost("FUEL", amount=None, liters="52.35", price_per_liter="61.75", odometer="12500"),
        cost(),
        cost("PARKING", amount="100.00"),
        cost("DRIVER_ALLOWANCE", amount="500.00"),
    ]:
        r = await submit(client, trip, data)
        assert r.status_code == 200, r.text
        result = r.json()["result"]
        ids.append(result["expense"]["id"])
        trip["version"] = result["trip_version"]
    summary = (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()
    assert summary["submitted_total"] == "4182.61"
    assert summary["reviewed_total"] == "0.00"
    await client.post("/api/v1/auth/logout")
    await login(client)
    for identifier in ids:
        r = await client.post(
            f"/api/v1/expenses/{identifier}/review",
            json={"expected_version": trip["version"], "notes": "Reviewed receipt"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 200, r.text
        trip["version"] = r.json()["result"]["trip_version"]
    summary = (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()
    assert summary["reviewed_total"] == "4182.61"
    r = await client.post(
        f"/api/v1/expenses/{ids[1]}/correct",
        json={
            **cost(amount="300.00"),
            "expected_version": trip["version"],
            "reason": "Receipt correction",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, r.text
    item = r.json()["result"]["expense"]
    assert [v["amount"] for v in item["revisions"]] == ["350.00", "300.00"]
    trip["version"] = r.json()["result"]["trip_version"]
    r = await client.post(
        f"/api/v1/expenses/{ids[2]}/void",
        json={"expected_version": trip["version"], "reason": "Duplicate parking"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, r.text
    summary = (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()
    assert summary["submitted_total"] == "4032.61"
    history = (await client.get(f"/api/v1/vehicles/{fleet['vehicles']['id']}/fuel-history")).json()
    assert history["items"][0]["amount"] == "3232.61"
    assert (
        await admin_db.scalar(text("SELECT count(*) FROM audit_logs WHERE action LIKE 'expense.%'"))
    ) == 10


@pytest.mark.parametrize(
    "category",
    [
        "TOLL",
        "PARKING",
        "DRIVER_ALLOWANCE",
        "DRIVER_CASH_ADVANCE",
        "HELPER_ALLOWANCE",
        "LOADING_FEE",
        "UNLOADING_FEE",
        "SUBCONTRACTOR",
        "OTHER",
    ],
)
async def test_categories_and_concurrent_replay(client, category):
    trip, _, _ = await setup(client)
    data = cost(category, description="Operational fee", vendor_name="Local supplier")
    key = str(uuid.uuid4())
    envelope = body(trip["version"], data)
    responses = await asyncio.gather(
        *(send(client, trip["id"], "expense", envelope, key) for _ in range(2))
    )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert {r.json()["outcome"] for r in responses} == {"APPLIED", "ALREADY_APPLIED"}
    assert (await client.get(f"/api/v1/trips/{trip['id']}/expenses")).json()["total"] == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"amount": 12.34},
        {"amount": "NaN"},
        {"amount": "-1.00"},
        {"amount": "0.00"},
        {"amount": "0.001"},
        {"amount": "10000000.01"},
        {"currency": "USD"},
        {"category": "OTHER"},
        {"category": "FUEL", "liters": "1", "price_per_liter": "1"},
        {"driver_id": str(uuid.uuid4())},
    ],
)
async def test_invalid_costs(client, fields):
    trip, _, _ = await setup(client)
    r = await submit(client, trip, cost(**fields))
    assert r.status_code == 422, r.text


async def test_private_receipt_replay(client):
    trip, _, _ = await setup(client)
    r = await submit(client, trip, cost())
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    identifier = result["expense"]["id"]
    params = {"expected_version": result["trip_version"], "filename": "receipt.png"}
    key = str(uuid.uuid4())
    for outcome in ("APPLIED", "ALREADY_APPLIED"):
        r = await client.post(
            f"/api/v1/expenses/{identifier}/evidence",
            params=params,
            content=image_bytes(),
            headers={"Idempotency-Key": key, "Content-Type": "image/png"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["outcome"] == outcome
    evidence = r.json()["result"]["evidence_id"]
    assert (await client.get(f"/api/v1/expense-evidence/{evidence}")).status_code == 200
    await client.post("/api/v1/auth/logout")
    assert (await client.get(f"/api/v1/expense-evidence/{evidence}")).status_code == 401


@pytest.mark.parametrize(
    "liters,price,total",
    [
        ("1", "0.005", "0.01"),
        ("0.1", "0.1", "0.01"),
        ("1.001", "1.0001", "1.00"),
        ("52.35", "61.75", "3232.61"),
    ],
)
async def test_rounding(client, liters, price, total):
    trip, _, _ = await setup(client)
    r = await submit(client, trip, cost("FUEL", amount=None, liters=liters, price_per_liter=price))
    assert r.status_code == 200, r.text
    assert r.json()["result"]["expense"]["current"]["amount"] == total


async def test_odometer_and_history_guards(client, admin_db):
    trip, identity, fleet = await setup(client)
    await admin_db.execute(
        text("UPDATE vehicles SET odometer=5000 WHERE id=:id"), {"id": fleet["vehicles"]["id"]}
    )
    await admin_db.commit()
    assert (
        await submit(
            client,
            trip,
            cost("FUEL", amount=None, liters="10", price_per_liter="60", odometer="4999"),
        )
    ).status_code == 409
    r = await submit(
        client, trip, cost("FUEL", amount=None, liters="10", price_per_liter="60", odometer="5500")
    )
    assert r.status_code == 200, r.text
    identifier = r.json()["result"]["expense"]["id"]
    trip["version"] = r.json()["result"]["trip_version"]
    assert (
        await admin_db.scalar(
            text("SELECT odometer FROM vehicles WHERE id=:id"), {"id": fleet["vehicles"]["id"]}
        )
        == 5000
    )
    for sql in (
        "UPDATE expense_revisions SET amount=1",
        "DELETE FROM expense_revisions",
        "UPDATE trip_expenses SET trip_id=:id",
    ):
        with pytest.raises(DBAPIError):
            await admin_db.execute(text(sql), {"id": uuid.uuid4()})
        await admin_db.rollback()
    async with Session() as db:
        await set_context(db, identity["user"]["id"], identity["organization"]["id"])
        with pytest.raises(DBAPIError):
            await db.execute(
                text(
                    "UPDATE trip_expenses SET status='REVIEWED',reviewed_by=:actor,reviewed_at=now()"
                ),
                {"actor": identity["user"]["id"]},
            )
        await db.rollback()
    await client.post("/api/v1/auth/logout")
    await login(client)
    r = await client.post(
        f"/api/v1/expenses/{identifier}/review",
        json={"expected_version": trip["version"]},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200, r.text
    trip["version"] = r.json()["result"]["trip_version"]
    r = await client.post(
        f"/api/v1/trips/{trip['id']}/expenses",
        json={
            **cost("FUEL", amount=None, liters="10", price_per_liter="60", odometer="5499"),
            "expected_version": trip["version"],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 409, r.text


@pytest.mark.parametrize(
    "filename,mime,data",
    [
        ("bad.exe", "image/png", b"MZ"),
        ("wrong.jpg", "image/jpeg", image_bytes()),
        ("../receipt.png", "image/png", image_bytes()),
        ("empty.png", "image/png", b""),
        ("script.svg", "image/svg+xml", b"<svg/>"),
        ("receipt.png", "text/html", image_bytes()),
        ("huge.png", "image/png", b"x" * (5242881)),
    ],
    ids=["executable", "spoof", "traversal", "empty", "svg", "mime", "oversize"],
)
async def test_receipt_attacks(client, filename, mime, data):
    trip, _, _ = await setup(client)
    created = (await submit(client, trip, cost())).json()["result"]
    r = await client.post(
        f"/api/v1/expenses/{created['expense']['id']}/evidence",
        params={"filename": filename, "expected_version": created["trip_version"]},
        content=data,
        headers={"Content-Type": mime, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code in (413, 415, 422), r.text


@pytest.mark.parametrize("foreign", ["tenant", "driver"])
async def test_adversarial_expense_and_direct_rls(client, admin_db, foreign):
    trip, identity, fleet = await setup(client)
    created = (await submit(client, trip, cost())).json()["result"]
    identifier = created["expense"]["id"]
    upload = await client.post(
        f"/api/v1/expenses/{identifier}/evidence",
        params={"filename": "receipt.png", "expected_version": created["trip_version"]},
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert upload.status_code == 200, upload.text
    evidence = upload.json()["result"]["evidence_id"]
    if foreign == "driver":
        user = uuid.uuid4()
        await admin_db.execute(
            text(
                "INSERT INTO users(id,name,email,hashed_password,is_active,is_verified,is_superuser,status) SELECT :id,'Pedro','pedro-cost@example.com',hashed_password,true,true,false,'ACTIVE' FROM users WHERE id=:juan"
            ),
            {"id": user, "juan": identity["user"]["id"]},
        )
        await admin_db.execute(
            text(
                "INSERT INTO organization_memberships(id,organization_id,user_id,role,active) VALUES(:id,:org,:user,'DRIVER',true)"
            ),
            {"id": uuid.uuid4(), "org": identity["organization"]["id"], "user": user},
        )
        await admin_db.commit()
    await client.post("/api/v1/auth/logout")
    await login(
        client, "other-owner@example.com" if foreign == "tenant" else "pedro-cost@example.com"
    )
    attacker = (await client.get("/api/v1/me")).json()
    for path in (
        f"/expenses/{identifier}",
        f"/trips/{trip['id']}/expenses",
        f"/expense-evidence/{evidence}",
        f"/vehicles/{fleet['vehicles']['id']}/fuel-history",
    ):
        r = await client.get("/api/v1" + path)
        assert r.status_code in (403, 404), r.text
    for action, payload in [
        ("review", {}),
        ("void", {"reason": "Attack"}),
        ("correct", cost(reason="Attack")),
    ]:
        r = await client.post(
            f"/api/v1/expenses/{identifier}/{action}",
            json={"expected_version": created["trip_version"], **payload},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code in (403, 404), r.text
    r = await client.post(
        f"/api/v1/expenses/{identifier}/evidence",
        params={"filename": "receipt.png", "expected_version": created["trip_version"]},
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code in (403, 404), r.text
    r = await client.post(
        f"/api/v1/trips/{trip['id']}/expenses",
        json={**cost(), "expected_version": created["trip_version"]},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code in (403, 404), r.text
    async with Session() as db:
        await set_context(db, attacker["user"]["id"], attacker["organization"]["id"])
        for table in ("trip_expenses", "expense_revisions", "expense_evidence"):
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0
            flags = (
                await admin_db.execute(
                    text(
                        "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname=:name"
                    ),
                    {"name": table},
                )
            ).one()
            assert all(flags)


async def test_review_denied_driver_closed_and_atomic_failure(client, admin_db, monkeypatch):
    from fleetpilot import expense_routes

    trip, _, _ = await setup(client)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic audit failure")

    with monkeypatch.context() as m:
        m.setattr(expense_routes, "audit", fail)
        assert (await submit(client, trip, cost())).status_code == 500
    assert await admin_db.scalar(text("SELECT count(*) FROM trip_expenses")) == 0
    assert (
        await admin_db.scalar(
            text("SELECT count(*) FROM driver_sync_commands WHERE command_type='expense'")
        )
        == 0
    )
    r = await submit(client, trip, cost())
    created = r.json()["result"]
    r = await client.post(
        f"/api/v1/expenses/{created['expense']['id']}/review",
        json={"expected_version": created["trip_version"]},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 403
    await client.post("/api/v1/auth/logout")
    await login(client)
    r = await client.post(
        f"/api/v1/trips/{trip['id']}/cancel",
        json={"expected_version": created["trip_version"], "reason": "Cancelled by customer"},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/trips/{trip['id']}/expenses",
        json={**cost(), "expected_version": r.json()["version"]},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 409
