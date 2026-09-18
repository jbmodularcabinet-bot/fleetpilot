import asyncio
import os
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context
from fleetpilot.master_models import Driver

from .conftest import login
from .delivery_helpers import image_bytes
from .test_master_data import DATA, fleet
from .test_trips import create_trip, finish

pytestmark = pytest.mark.asyncio


async def setup(client, stop="dispatch"):
    await login(client, "juan@example.com")
    identity = (await client.get("/api/v1/me")).json()
    await client.post("/api/v1/auth/logout")
    await login(client)
    rows = await fleet(client)
    response = await client.patch(
        f"/api/v1/drivers/{rows['drivers']['id']}",
        json={**DATA["drivers"], "user_id": identity["user"]["id"]},
    )
    assert response.status_code == 200
    trip = await finish(client, await create_trip(client, rows), stop)
    await client.post("/api/v1/auth/logout")
    await login(client, "juan@example.com")
    return trip, identity, rows


def body(version, payload=None, resource=None):
    return {
        "expected_version": version,
        "occurred_at_client": datetime.now(timezone.utc).isoformat(),
        "resource_id": resource,
        "payload": payload or {},
    }


async def send(client, trip, command, data, key=None):
    return await client.post(
        f"/api/v1/driver/sync/{trip}/{command}",
        json=data,
        headers={"Idempotency-Key": key or str(uuid.uuid4())},
    )


async def test_replay_lost_response_concurrent_and_persistent(client, admin_db):
    trip, identity, _ = await setup(client)
    data = body(trip["version"], {"action": "start_pickup"})
    key = str(uuid.uuid4())
    replies = await asyncio.gather(
        *(send(client, trip["id"], "transition", data, key) for _ in range(3))
    )
    assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
    assert sorted(r.json()["outcome"] for r in replies) == [
        "ALREADY_APPLIED",
        "ALREADY_APPLIED",
        "APPLIED",
    ]
    assert len({r.json()["result"]["version"] for r in replies}) == 1
    events = (await client.get(f"/api/v1/driver/trips/{trip['id']}/milestones")).json()
    assert sum(e["milestone_type"] == "EN_ROUTE_TO_PICKUP" for e in events) == 1
    # New session/connection, not process memory, stores the replay result and times.
    async with Session() as db:
        await set_context(db, identity["user"]["id"], identity["organization"]["id"])
        row = (await db.execute(text("SELECT * FROM driver_sync_commands"))).mappings().one()
        assert row["occurred_at_client"] and row["received_at_server"] and row["result"]
    assert (
        await send(
            client, trip["id"], "transition", {**data, "payload": {"action": "arrive_pickup"}}, key
        )
    ).status_code == 409


@pytest.mark.parametrize("bad", ["deliver", "dispatch", "finish_loading", "unknown"])
async def test_invalid_offline_transitions(client, bad):
    trip, _, _ = await setup(client)
    assert (
        await send(client, trip["id"], "transition", body(trip["version"], {"action": bad}))
    ).status_code in {403, 409, 422}


async def test_stale_version_and_tampered_identity(client):
    trip, _, _ = await setup(client)
    assert (
        await send(
            client, trip["id"], "transition", body(trip["version"] - 1, {"action": "start_pickup"})
        )
    ).status_code == 409
    data = {
        **body(trip["version"], {"action": "start_pickup"}),
        "organization_id": str(uuid.uuid4()),
    }
    assert (await send(client, trip["id"], "transition", data)).status_code == 422
    data = body(trip["version"], {"action": "start_pickup", "driver_id": str(uuid.uuid4())})
    assert (await send(client, trip["id"], "transition", data)).status_code == 422


@pytest.mark.parametrize("exception", [False, True])
async def test_delivery_commands_replay_once(client, admin_db, exception):
    trip, _, _ = await setup(client, "finish_unloading")
    key = str(uuid.uuid4())
    data = body(trip["version"])
    response = await send(client, trip["id"], "attempt", data, key)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert (await send(client, trip["id"], "attempt", data, key)).json()["result"] == result
    attempt = result["attempt"]["id"]
    version = result["trip_version"]
    for evidence_type in ["EXCEPTION_PHOTO"] if exception else ["DELIVERY_PHOTO", "SIGNATURE"]:
        key = str(uuid.uuid4())
        params = {
            "resource_id": attempt,
            "expected_version": version,
            "filename": "photo.png",
            "evidence_type": evidence_type,
            "occurred_at_client": datetime.now(timezone.utc).isoformat(),
        }
        for i in range(2):
            r = await client.post(
                f"/api/v1/driver/sync/{trip['id']}/evidence",
                params=params,
                content=image_bytes(),
                headers={"Idempotency-Key": key, "Content-Type": "image/png"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["outcome"] == ("APPLIED" if i == 0 else "ALREADY_APPLIED")
        version = r.json()["result"]["trip_version"]
    command = "exception" if exception else "pod"
    fields = (
        {"exception_type": "RECIPIENT_UNAVAILABLE", "notes": "Recipient contact unreachable."}
        if exception
        else {
            "recipient_name": "Maria Santos",
            "driver_confirmed": True,
            "signature_confirmed": True,
        }
    )
    data = body(version, fields, attempt)
    key = str(uuid.uuid4())
    first = await send(client, trip["id"], command, data, key)
    assert first.status_code == 200, first.text
    assert (await send(client, trip["id"], command, data, key)).json()["result"] == first.json()[
        "result"
    ]
    history = (await client.get(f"/api/v1/trips/{trip['id']}/delivery-attempts")).json()
    assert history["total"] == 1
    assert len(history["items"][0]["evidence"]) == (1 if exception else 2)
    authoritative = (await client.get(f"/api/v1/driver/trips/{trip['id']}")).json()
    assert (authoritative["current_status"] == "DELIVERED") is not exception
    assert (await send(client, trip["id"], command, data)).status_code == 409


async def test_replay_reauthorizes_driver_and_rls(client, admin_db):
    trip, identity, rows = await setup(client)
    data = body(trip["version"], {"action": "start_pickup"})
    key = str(uuid.uuid4())
    assert (await send(client, trip["id"], "transition", data, key)).status_code == 200
    await admin_db.execute(
        text("UPDATE drivers SET user_id=NULL WHERE id=:id"), {"id": rows["drivers"]["id"]}
    )
    await admin_db.commit()
    assert (await send(client, trip["id"], "transition", data, key)).status_code == 404
    async with Session() as db:
        await set_context(db, str(uuid.uuid4()), identity["organization"]["id"])
        assert (await db.execute(text("SELECT * FROM driver_sync_commands"))).all() == []
        await set_context(db, identity["user"]["id"], str(uuid.uuid4()))
        assert (await db.execute(text("SELECT * FROM driver_sync_commands"))).all() == []


async def test_cross_tenant_and_owner_cannot_replay(client):
    trip, _, _ = await setup(client)
    data = body(trip["version"], {"action": "start_pickup"})
    key = str(uuid.uuid4())
    assert (await send(client, trip["id"], "transition", data, key)).status_code == 200
    await client.post("/api/v1/auth/logout")
    await login(client)
    assert (await send(client, trip["id"], "transition", data, key)).status_code == 403
    assert (await client.get("/api/v1/driver/offline-identity")).status_code == 403


async def test_audit_failure_rolls_back_receipt_and_transition(client, admin_db):
    trip, _, _ = await setup(client)
    await admin_db.execute(
        text(
            "CREATE FUNCTION reject_sync_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fault'; END $$"
        )
    )
    await admin_db.execute(
        text(
            "CREATE TRIGGER reject_sync_audit BEFORE INSERT ON audit_logs FOR EACH ROW EXECUTE FUNCTION reject_sync_audit()"
        )
    )
    await admin_db.commit()
    data = body(trip["version"], {"action": "start_pickup"})
    key = str(uuid.uuid4())
    try:
        assert (await send(client, trip["id"], "transition", data, key)).status_code == 500
    finally:
        await admin_db.execute(text("DROP TRIGGER reject_sync_audit ON audit_logs"))
        await admin_db.execute(text("DROP FUNCTION reject_sync_audit()"))
        await admin_db.commit()
    assert (await send(client, trip["id"], "transition", data, key)).json()["outcome"] == "APPLIED"


async def test_command_survives_real_api_process_restart(client):
    trip, _, _ = await setup(client)
    data = body(trip["version"], {"action": "start_pickup"})
    key = str(uuid.uuid4())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    for expected in ["APPLIED", "ALREADY_APPLIED"]:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "fleetpilot.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}", headers={"Origin": "http://localhost:3000"}
            ) as remote:
                for _ in range(100):
                    try:
                        if (await remote.get("/health")).status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    await asyncio.sleep(0.1)
                response = await remote.post(
                    "/api/v1/auth/login",
                    data={"username": "juan@example.com", "password": os.environ["DEMO_PASSWORD"]},
                )
                assert response.status_code == 204
                result = await send(remote, trip["id"], "transition", data, key)
                assert result.status_code == 200, result.text
                assert result.json()["outcome"] == expected
        finally:
            process.terminate()
            process.wait(timeout=10)


@pytest.mark.parametrize("email", ["carlo@example.com", "other-owner@example.com"])
async def test_other_linked_driver_cannot_sync_known_ids(client, admin_db, email):
    trip, identity, _ = await setup(client)
    key = str(uuid.uuid4())
    data = body(trip["version"], {"action": "start_pickup"})
    assert (await send(client, trip["id"], "transition", data, key)).status_code == 200
    row = (
        (
            await admin_db.execute(
                text(
                    "SELECT u.id, m.organization_id FROM users u JOIN organization_memberships m ON m.user_id=u.id WHERE u.email=:email"
                ),
                {"email": email},
            )
        )
        .mappings()
        .one()
    )
    await admin_db.execute(
        text("UPDATE organization_memberships SET role='DRIVER' WHERE user_id=:user"),
        {"user": row["id"]},
    )
    admin_db.add(
        Driver(
            organization_id=row["organization_id"],
            user_id=row["id"],
            employee_number="DRV-B",
            first_name="Pedro",
            last_name="Reyes",
            created_by=row["id"],
            updated_by=row["id"],
        )
    )
    await admin_db.commit()
    await client.post("/api/v1/auth/logout")
    await login(client, email)
    assert (await client.get("/api/v1/driver/offline-identity")).json()["driver_id"]
    for command in ["transition", "attempt", "pod", "exception"]:
        assert (await send(client, trip["id"], command, data, key)).status_code == 404
    r = await client.post(
        f"/api/v1/driver/sync/{trip['id']}/evidence",
        params={
            "resource_id": str(uuid.uuid4()),
            "expected_version": trip["version"],
            "filename": "photo.png",
            "occurred_at_client": datetime.now(timezone.utc).isoformat(),
        },
        content=image_bytes(),
        headers={"Idempotency-Key": key, "Content-Type": "image/png"},
    )
    assert r.status_code == 404
    async with Session() as db:
        await set_context(db, str(row["id"]), str(row["organization_id"]))
        assert (await db.execute(text("SELECT * FROM driver_sync_commands"))).all() == []
    async with Session() as db:
        await set_context(db, identity["user"]["id"], identity["organization"]["id"])
        denied = await db.execute(text("UPDATE driver_sync_commands SET request_hash='tamper'"))
        assert denied.rowcount == 0
        assert (
            await db.scalar(
                text("SELECT count(*) FROM driver_sync_commands WHERE request_hash='tamper'")
            )
            == 0
        )
    with pytest.raises(DBAPIError):
        await admin_db.execute(text("UPDATE driver_sync_commands SET request_hash='tamper'"))
    await admin_db.rollback()


async def test_client_clock_is_preserved_but_never_controls_audit_time(client, admin_db):
    trip, _, _ = await setup(client)
    data = body(trip["version"], {"action": "start_pickup"})
    data["occurred_at_client"] = "1990-01-01T00:00:00Z"
    assert (await send(client, trip["id"], "transition", data)).status_code == 200
    row = (
        (
            await admin_db.execute(
                text(
                    "SELECT occurred_at_client,received_at_server,clock_suspect FROM driver_sync_commands"
                )
            )
        )
        .mappings()
        .one()
    )
    assert row["clock_suspect"] and row["occurred_at_client"].year == 1990
    assert row["received_at_server"].year == datetime.now(timezone.utc).year
    history = (await client.get(f"/api/v1/driver/trips/{trip['id']}/milestones")).json()
    assert not history[-1]["occurred_at"].startswith("1990")
