import uuid

import pytest
from sqlalchemy import text

from fleetpilot.db import Session, set_context

from .test_adjustments import adjustment, apply, completed, reverse
from .test_expenses import cost, submit
from .test_sync import setup

pytestmark = pytest.mark.asyncio


async def test_open_trip_and_nonfuel_odometer_are_rejected(client):
    trip, _, _ = await setup(client)
    result = (await submit(client, trip, cost())).json()["result"]
    from .conftest import login

    await client.post("/api/v1/auth/logout")
    await login(client)
    assert (await apply(client, trip, adjustment(result["expense"]["id"]))).status_code == 409


async def test_permission_revocation_blocks_replay(client, admin_db):
    trip, ids, _, _ = await completed(client)
    who = (await client.get("/api/v1/me")).json()
    key = str(uuid.uuid4())
    data = adjustment(ids[1])
    assert (await apply(client, trip, data, key)).status_code == 200
    await admin_db.execute(
        text(
            "UPDATE organization_memberships SET permissions_json=CAST(:permissions AS jsonb) WHERE user_id=:actor AND organization_id=:org"
        ),
        dict(
            permissions='{"deny":["closed_trip_adjustments.create"]}',
            actor=uuid.UUID(who["user"]["id"]),
            org=uuid.UUID(who["organization"]["id"]),
        ),
    )
    await admin_db.commit()
    assert (await apply(client, trip, data, key)).status_code == 403


async def test_target_identity_mass_assignment_and_duplicate_key(client):
    trip, ids, _, _ = await completed(client)
    key = str(uuid.uuid4())
    assert (
        await apply(client, trip, {**adjustment(ids[1]), "organization_id": str(uuid.uuid4())})
    ).status_code == 422
    assert (
        await apply(client, trip, adjustment(ids[1], kind="CATEGORY_CORRECTION", value="FUEL"))
    ).status_code == 422
    assert (
        await apply(client, trip, adjustment(ids[1], kind="ODOMETER_CORRECTION", value="12345.0"))
    ).status_code == 422
    assert (await apply(client, trip, adjustment(ids[1]), key)).status_code == 200
    assert (
        await apply(client, trip, adjustment(ids[1], 1, value="400.00"), key)
    ).status_code == 409


async def test_forced_rls_and_append_only_deletion(client, admin_db):
    trip, ids, _, _ = await completed(client)
    result = await apply(client, trip, adjustment(ids[1]))
    assert result.status_code == 200
    who = (await client.get("/api/v1/me")).json()
    for table in ["closed_trip_adjustments", "expense_effective_values"]:
        forced = await admin_db.scalar(
            text(
                "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname=:table"
            ),
            {"table": table},
        )
        assert forced
    async with Session() as db:
        await set_context(db, who["user"]["id"], who["organization"]["id"])
        for table in ["closed_trip_adjustments", "expense_effective_values"]:
            assert (await db.execute(text(f"DELETE FROM {table}"))).rowcount == 0
        assert await db.scalar(text("SELECT count(*) FROM closed_trip_adjustments")) == 1
    assert (await reverse(client, result.json()["result"]["adjustment_id"], 1)).status_code == 200
