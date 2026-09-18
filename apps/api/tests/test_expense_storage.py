import uuid

import httpx
import pytest
from sqlalchemy import text

from fleetpilot.storage_admin import reconcile, restore_objects, snapshot

from . import test_hardening
from .delivery_helpers import image_bytes
from .test_expenses import cost, submit
from .test_sync import setup

s3_store = test_hardening.s3_store
pytestmark = pytest.mark.asyncio


async def test_expense_private_s3_reconcile_snapshot_restore(
    client, admin_db, monkeypatch, s3_store, tmp_path
):
    monkeypatch.setattr("fleetpilot.expense_routes.storage", lambda: s3_store)
    trip, _, _ = await setup(client)
    result = (await submit(client, trip, cost())).json()["result"]
    response = await client.post(
        f"/api/v1/expenses/{result['expense']['id']}/evidence",
        params={"filename": "receipt.png", "expected_version": result["trip_version"]},
        content=image_bytes(),
        headers={"Content-Type": "image/png", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    identifier = response.json()["result"]["evidence_id"]
    assert (await client.get(f"/api/v1/expense-evidence/{identifier}")).status_code == 200
    records = (
        (
            await admin_db.execute(
                text("SELECT id,storage_key,checksum,status FROM expense_evidence")
            )
        )
        .mappings()
        .all()
    )
    async with httpx.AsyncClient() as anonymous:
        r = await anonymous.get(
            f"http://127.0.0.1:9000/{s3_store.bucket}/{records[0]['storage_key']}"
        )
        assert r.status_code in (403, 404)
    assert all(not values for values in reconcile(records, s3_store).values())
    destination = tmp_path / "receipt-backup"
    snapshot(records, s3_store, destination)
    # Only the fixture's disposable bucket is altered, then restored and checked.
    assert s3_store.bucket.startswith("fp-test-")
    s3_store.discard_uncommitted(records[0]["storage_key"])
    assert reconcile(records, s3_store)["missing"] == [identifier]
    restore_objects(destination, s3_store)
    assert all(not values for values in reconcile(records, s3_store).values())
    assert (await client.get(f"/api/v1/expense-evidence/{identifier}")).status_code == 200
