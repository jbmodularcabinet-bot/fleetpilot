import asyncio
import io
import uuid

import pytest
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from fleetpilot.db import Session, set_context
from fleetpilot.evidence_storage import LocalEvidenceStorage, storage

from .conftest import login
from .delivery_helpers import image_bytes, review_delivery, upload
from .test_master_data import DATA, create, fleet
from .test_trips import act, create_trip, finish

pytestmark = pytest.mark.asyncio


async def setup(client, stop="finish_unloading"):
    await login(client)
    rows = await fleet(client)
    trip = await finish(client, await create_trip(client, rows), stop=stop)
    return rows, trip


async def start(client, trip):
    response = await client.post(
        f"/api/v1/trips/{trip['id']}/delivery-attempts", json={"expected_version": trip["version"]}
    )
    assert response.status_code == 201, response.text
    return response.json()


def pod_body(version, **extra):
    return {
        "expected_version": version,
        "recipient_name": "Maria Santos",
        "recipient_role": "Receiving Staff",
        "driver_confirmed": True,
        "notes": "Cargo received in good condition.",
        **extra,
    }


async def successful(client, trip, signature=True, recipient="Maria Santos"):
    attempt = await start(client, trip)
    photo = await upload(client, attempt["attempt"]["id"], attempt["trip_version"])
    version = photo["trip_version"]
    signature_row = None
    if signature:
        signature_row = await upload(client, attempt["attempt"]["id"], version, "SIGNATURE")
        version = signature_row["trip_version"]
    result = await client.post(
        f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod",
        json=pod_body(version, signature_confirmed=signature, recipient_name=recipient),
    )
    assert result.status_code == 201, result.text
    return attempt, photo, signature_row, result.json()


async def test_successful_delivery_golden_and_review(client, admin_db):
    _, trip = await setup(client)
    attempt, photo, signature, result = await successful(client, trip)
    trip, pod = result["trip"], result["pod"]
    assert trip["current_status"] == "DELIVERED" and trip["completed_at"] is None
    assert pod["recipient_name"] == "Maria Santos" and pod["driver_confirmed"]
    assert pod["signature_evidence_id"] == signature["evidence"]["id"]
    for evidence in (photo["evidence"], signature["evidence"]):
        metadata = await client.get("/api/v1/evidence/" + evidence["id"] + "/metadata")
        assert metadata.status_code == 200 and "storage_key" not in metadata.json()
        assert "storage_key" not in evidence
        response = await client.get("/api/v1/evidence/" + evidence["id"])
        assert response.status_code == 200 and response.headers["content-type"] == "image/png"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert Image.open(io.BytesIO(response.content)).size == (64, 48)
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/complete",
            json={"expected_version": trip["version"], "closeout_reviewed": True},
        )
    ).status_code == 409
    trip = await review_delivery(client, trip)
    result = await client.post(
        f"/api/v1/trips/{trip['id']}/complete",
        json={"expected_version": trip["version"], "closeout_reviewed": True},
    )
    assert result.status_code == 200
    history = (await client.get(f"/api/v1/trips/{trip['id']}/delivery-attempts")).json()
    row = history["items"][0]
    assert history["total"] == 1 and row["status"] == "DELIVERED"
    assert (
        row["pod"]["status"] == "REVIEWED"
        and row["pod"]["reviewed_at"]
        and row["pod"]["reviewed_by"]
    )
    assert len(row["evidence"]) == 2 and row["completed_at"]
    logs = (
        await client.get(f"/api/v1/audit-logs?entity_type=trip&entity_id={trip['id']}&limit=100")
    ).json()
    assert {
        "delivery_attempt.created",
        "delivery_attempt.delivered",
        "evidence.uploaded",
        "pod.submitted",
        "pod.reviewed",
        "trip.delivered",
        "trip.completed",
    } <= {row["action"] for row in logs}
    assert not any("storage_key" in str(row) for row in logs)
    for table, identifier in [
        ("delivery_attempts", attempt["attempt"]["id"]),
        ("proof_of_delivery", pod["id"]),
        ("delivery_evidence", photo["evidence"]["id"]),
    ]:
        with pytest.raises(DBAPIError):
            await admin_db.execute(
                text(f"UPDATE {table} SET created_by=created_by WHERE id=:id")
                if table == "delivery_attempts"
                else text(f"UPDATE {table} SET status=status WHERE id=:id"),
                {"id": identifier},
            )
        await admin_db.rollback()
        with pytest.raises(DBAPIError):
            await admin_db.execute(text(f"DELETE FROM {table} WHERE id=:id"), {"id": identifier})
        await admin_db.rollback()


async def test_failed_retry_golden_preserves_original(client, admin_db):
    _, trip = await setup(client, stop="arrive_delivery")
    attempt = await start(client, trip)
    photo = await upload(
        client, attempt["attempt"]["id"], attempt["trip_version"], "EXCEPTION_PHOTO"
    )
    failed = await client.post(
        f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/exception",
        json={
            "expected_version": photo["trip_version"],
            "exception_type": "RECIPIENT_UNAVAILABLE",
            "notes": "Recipient contact unreachable.",
        },
    )
    assert failed.status_code == 201, failed.text
    issue = failed.json()["exception"]
    trip = (await client.get(f"/api/v1/trips/{trip['id']}")).json()
    assert trip["current_status"] == "IN_TRANSIT" and trip["next_action"] is None
    assert await admin_db.scalar(text("SELECT count(*) FROM proof_of_delivery")) == 0
    before = (await client.get(f"/api/v1/delivery-attempts/{attempt['attempt']['id']}")).json()
    assert before["status"] == "FAILED" and before["pod"] is None
    with pytest.raises(DBAPIError):
        await admin_db.execute(
            text("UPDATE delivery_attempts SET status='DELIVERED' WHERE id=:id"),
            {"id": attempt["attempt"]["id"]},
        )
    await admin_db.rollback()
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/transition",
            json={"expected_version": trip["version"], "action": "start_unloading"},
        )
    ).status_code == 409
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/delivery-attempts",
            json={"expected_version": trip["version"]},
        )
    ).status_code == 409
    resolved = await client.post(
        f"/api/v1/delivery-exceptions/{issue['id']}/resolve",
        json={
            "expected_version": trip["version"],
            "resolution_notes": "Recipient is now present. Retry at the same stop.",
        },
    )
    assert resolved.status_code == 200, resolved.text
    trip = (await client.get(f"/api/v1/trips/{trip['id']}")).json()
    trip = await act(client, trip, "start_unloading")
    trip = await act(client, trip, "finish_unloading")
    second, _, _, result = await successful(client, trip, signature=False, recipient="Pedro Reyes")
    assert result["pod"]["recipient_name"] == "Pedro Reyes"
    assert (
        second["attempt"]["attempt_number"] == 2 and result["trip"]["current_status"] == "DELIVERED"
    )
    original = (await client.get(f"/api/v1/delivery-attempts/{attempt['attempt']['id']}")).json()
    for key in ("status", "arrived_at", "completed_at", "created_by", "created_at", "evidence"):
        assert original[key] == before[key]
    assert original["exception"]["notes"] == "Recipient contact unreachable."
    assert original["exception"]["status"] == "RETRY_AUTHORIZED"
    assert (await client.get(f"/api/v1/evidence/{photo['evidence']['id']}")).status_code == 200
    milestones = (await client.get(f"/api/v1/trips/{trip['id']}/milestones")).json()
    assert {"DELIVERY_ATTEMPT_FAILED", "DELIVERY_RETRY_AUTHORIZED", "DELIVERY_RETRY_STARTED"} <= {
        row["milestone_type"] for row in milestones
    }
    page = (
        await client.get(f"/api/v1/trips/{trip['id']}/delivery-attempts?limit=1&offset=1")
    ).json()
    assert page["total"] == 2 and page["items"][0]["attempt_number"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"recipient_name": ""},
        {"recipient_name": "   "},
        {"driver_confirmed": False},
        {"organization_id": str(uuid.uuid4())},
        {"confirmed_at": "2030-01-01T00:00:00Z"},
        {"status": "REVIEWED"},
    ],
)
async def test_pod_validation_and_mass_assignment(client, changes):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    response = await client.post(
        f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod",
        json=pod_body(attempt["trip_version"], **changes),
    )
    assert response.status_code == 422
    assert (await client.get(f"/api/v1/trips/{trip['id']}")).json()[
        "current_status"
    ] == "IN_TRANSIT"


@pytest.mark.parametrize(
    "filename,mime,content",
    [
        ("bad.exe", "image/png", b"MZbad"),
        ("wrong.jpg", "image/jpeg", image_bytes()),
        ("../photo.png", "image/png", image_bytes()),
        ("empty.png", "image/png", b""),
        ("script.svg", "image/svg+xml", b"<svg/>"),
        ("broken.png", "image/png", b"\x89PNG\r\n\x1a\ninvalid"),
        ("photo.png", "text/html", image_bytes()),
    ],
)
async def test_invalid_uploads(client, filename, mime, content):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    response = await client.post(
        f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
        params={"expected_version": attempt["trip_version"], "filename": filename},
        content=content,
        headers={"Content-Type": mime},
    )
    assert response.status_code == 422
    assert (await client.get(f"/api/v1/delivery-attempts/{attempt['attempt']['id']}")).json()[
        "evidence"
    ] == []


@pytest.mark.parametrize(
    "format,mime,extension",
    [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png"), ("WEBP", "image/webp", "webp")],
)
async def test_allowed_types_decoded_and_private(client, format, mime, extension):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    response = await client.post(
        f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
        params={"expected_version": attempt["trip_version"], "filename": f"photo.{extension}"},
        content=image_bytes(format) + b"UNTRUSTED APPENDED CONTENT",
        headers={"Content-Type": mime},
    )
    assert response.status_code == 201, response.text
    evidence = response.json()["evidence"]
    fetched = await client.get("/api/v1/evidence/" + evidence["id"])
    assert b"UNTRUSTED APPENDED CONTENT" not in fetched.content
    await client.post("/api/v1/auth/logout")
    assert (await client.get("/api/v1/evidence/" + evidence["id"])).status_code == 401
    assert (await client.get("/uploads/photo." + extension)).status_code == 404


async def test_size_pixel_animation_and_attempt_limits(client):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    path = f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence"
    params = {"expected_version": attempt["trip_version"], "filename": "photo.png"}
    assert (
        await client.post(
            path,
            params=params,
            content=b"x" * (5 * 1024 * 1024 + 1),
            headers={"Content-Type": "image/png"},
        )
    ).status_code == 413
    huge = io.BytesIO()
    Image.new("1", (4100, 4100)).save(huge, format="PNG")
    assert (
        await client.post(
            path, params=params, content=huge.getvalue(), headers={"Content-Type": "image/png"}
        )
    ).status_code == 422
    animated = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(
        animated,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGB", (4, 4), "blue")],
        duration=10,
        loop=0,
    )
    assert (
        await client.post(
            path, params=params, content=animated.getvalue(), headers={"Content-Type": "image/png"}
        )
    ).status_code == 422
    version = attempt["trip_version"]
    for _ in range(12):
        version = (await upload(client, attempt["attempt"]["id"], version))["trip_version"]
    assert (
        await client.post(
            path,
            params={**params, "expected_version": version},
            content=image_bytes(),
            headers={"Content-Type": "image/png"},
        )
    ).status_code == 409


async def test_required_photo_signature_and_supersession(client):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    path = f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod"
    assert (await client.post(path, json=pod_body(attempt["trip_version"]))).status_code == 422
    old = await upload(client, attempt["attempt"]["id"], attempt["trip_version"])
    replacement = await upload(
        client, attempt["attempt"]["id"], old["trip_version"], supersedes_id=old["evidence"]["id"]
    )
    signature = await upload(
        client, attempt["attempt"]["id"], replacement["trip_version"], "SIGNATURE"
    )
    assert (await client.post(path, json=pod_body(signature["trip_version"]))).status_code == 422
    result = await client.post(
        path, json=pod_body(signature["trip_version"], signature_confirmed=True)
    )
    assert result.status_code == 201
    evidence = (await client.get(f"/api/v1/delivery-attempts/{attempt['attempt']['id']}")).json()[
        "evidence"
    ]
    assert evidence[0]["status"] == "SUPERSEDED" and len(evidence) == 3
    assert (await client.get("/api/v1/evidence/" + old["evidence"]["id"])).status_code == 200
    assert (
        await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
            params={"expected_version": result.json()["trip"]["version"], "filename": "new.png"},
            content=image_bytes(),
            headers={"Content-Type": "image/png"},
        )
    ).status_code == 409


async def test_concurrent_submission_exception_and_review(client):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    photo = await upload(client, attempt["attempt"]["id"], attempt["trip_version"])
    path = f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod"
    results = await asyncio.gather(
        *(client.post(path, json=pod_body(photo["trip_version"])) for _ in range(2))
    )
    assert sorted(row.status_code for row in results) == [201, 409]
    result = next(row.json() for row in results if row.status_code == 201)
    results = await asyncio.gather(
        *(
            client.post(
                f"/api/v1/pod/{result['pod']['id']}/review",
                json={"expected_version": result["trip"]["version"]},
            )
            for _ in range(2)
        )
    )
    assert sorted(row.status_code for row in results) == [200, 409]
    assert (
        await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/exception",
            json={
                "expected_version": max(row.json().get("trip_version", 0) for row in results),
                "exception_type": "OTHER",
                "notes": "Cannot alter delivered attempt",
            },
        )
    ).status_code == 409


async def test_pod_and_upload_audit_failure_roll_back(client, admin_db, monkeypatch):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    photo = await upload(client, attempt["attempt"]["id"], attempt["trip_version"])
    await admin_db.execute(
        text(
            "CREATE FUNCTION reject_pod_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action IN ('pod.submitted','evidence.uploaded') THEN RAISE EXCEPTION 'test audit failure'; END IF; RETURN NEW; END $$"
        )
    )
    await admin_db.execute(
        text(
            "CREATE TRIGGER reject_pod_audit BEFORE INSERT ON audit_logs FOR EACH ROW EXECUTE FUNCTION reject_pod_audit()"
        )
    )
    await admin_db.commit()
    try:
        response = await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod",
            json=pod_body(photo["trip_version"]),
        )
        assert response.status_code == 500
        row = (await client.get(f"/api/v1/delivery-attempts/{attempt['attempt']['id']}")).json()
        assert row["status"] == "IN_PROGRESS" and row["pod"] is None
        assert (await client.get(f"/api/v1/trips/{trip['id']}")).json()["version"] == photo[
            "trip_version"
        ]
        root = storage().root
        before = set(root.rglob("*.png"))
        response = await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
            params={"expected_version": photo["trip_version"], "filename": "rollback.png"},
            content=image_bytes(),
            headers={"Content-Type": "image/png"},
        )
        assert response.status_code == 500
        assert set(root.rglob("*.png")) == before
    finally:
        await admin_db.execute(text("DROP TRIGGER reject_pod_audit ON audit_logs"))
        await admin_db.execute(text("DROP FUNCTION reject_pod_audit()"))
        await admin_db.commit()

    def fail_write(self, key, data):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(LocalEvidenceStorage, "put", fail_write)
    response = await client.post(
        f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
        params={"expected_version": photo["trip_version"], "filename": "fail.png"},
        content=image_bytes(),
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code == 500
    assert (
        len(
            (await client.get(f"/api/v1/delivery-attempts/{attempt['attempt']['id']}")).json()[
                "evidence"
            ]
        )
        == 1
    )


async def test_cross_tenant_and_direct_postgres_rls(client, admin_db):
    _, trip = await setup(client)
    attempt, photo, signature, result = await successful(client, trip)
    a = (await client.get("/api/v1/me")).json()
    await client.post("/api/v1/auth/logout")
    await login(client, "other-owner@example.com")
    rows_b = await fleet(client)
    trip_b = await finish(client, await create_trip(client, rows_b), stop="arrive_delivery")
    b = (await client.get("/api/v1/me")).json()
    attempt_b = await start(client, trip_b)
    failed = await client.post(
        f"/api/v1/delivery-attempts/{attempt_b['attempt']['id']}/exception",
        json={
            "expected_version": attempt_b["trip_version"],
            "exception_type": "OTHER",
            "notes": "Fixture issue",
        },
    )
    assert failed.status_code == 201
    for path in (
        f"/trips/{trip['id']}/delivery-attempts",
        f"/delivery-attempts/{attempt['attempt']['id']}",
        f"/pod/{result['pod']['id']}",
        f"/evidence/{photo['evidence']['id']}",
        f"/evidence/{photo['evidence']['id']}/metadata",
        f"/evidence/{signature['evidence']['id']}",
    ):
        assert (await client.get("/api/v1" + path)).status_code == 404
    for path, payload in [
        (f"/pod/{result['pod']['id']}/review", {"expected_version": result["trip"]["version"]}),
        (f"/delivery-attempts/{attempt['attempt']['id']}/pod", pod_body(result["trip"]["version"])),
        (
            f"/delivery-attempts/{attempt['attempt']['id']}/exception",
            {
                "expected_version": result["trip"]["version"],
                "exception_type": "RECIPIENT_UNAVAILABLE",
            },
        ),
    ]:
        assert (await client.post("/api/v1" + path, json=payload)).status_code == 404
    assert (
        await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
            params={"expected_version": 1, "filename": "foreign.png"},
            content=image_bytes(),
            headers={"Content-Type": "image/png"},
        )
    ).status_code == 404
    tables = ["delivery_attempts", "delivery_evidence", "proof_of_delivery", "delivery_exceptions"]
    async with Session() as db:
        for table in tables:
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        await set_context(db, b["user"]["id"], b["organization"]["id"])
        for table in tables:
            assert (
                await db.scalar(
                    text(f"SELECT count(*) FROM {table} WHERE organization_id=:org"),
                    {"org": a["organization"]["id"]},
                )
                == 0
            )
            assert (
                await db.execute(
                    text(f"UPDATE {table} SET status=status WHERE organization_id=:org"),
                    {"org": a["organization"]["id"]},
                )
            ).rowcount == 0
        assert await db.scalar(text("SELECT count(*) FROM delivery_attempts")) == 1
        assert await db.scalar(text("SELECT count(*) FROM delivery_exceptions")) == 1
        await db.rollback()
    for table in tables:
        assert (
            await admin_db.execute(
                text("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname=:name"),
                {"name": table},
            )
        ).one() == (True, True)
    assert (
        await client.get(f"/api/v1/delivery-exceptions/{failed.json()['exception']['id']}")
    ).status_code == 200
    # Reverse direction: A cannot resolve B's known exception UUID.
    await client.post("/api/v1/auth/logout")
    await login(client)
    assert (
        await client.get(f"/api/v1/delivery-exceptions/{failed.json()['exception']['id']}")
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/delivery-exceptions/{failed.json()['exception']['id']}/resolve",
            json={"expected_version": trip["version"], "resolution_notes": "Foreign retry"},
        )
    ).status_code == 404


async def test_same_tenant_other_driver_evidence_boundary(client, admin_db):
    await login(client, "juan@example.com")
    juan = (await client.get("/api/v1/me")).json()
    await client.post("/api/v1/auth/logout")
    await login(client)
    rows = await fleet(client)
    linked = await client.patch(
        f"/api/v1/drivers/{rows['drivers']['id']}",
        json={**DATA["drivers"], "user_id": juan["user"]["id"]},
    )
    assert linked.status_code == 200
    pedro_id = uuid.uuid4()
    await admin_db.execute(
        text(
            "INSERT INTO users (id,name,email,hashed_password,is_active,is_verified,is_superuser,status) SELECT :id,'Pedro Reyes','pedro@example.com',hashed_password,true,true,false,'ACTIVE' FROM users WHERE id=:juan"
        ),
        {"id": pedro_id, "juan": juan["user"]["id"]},
    )
    await admin_db.execute(
        text(
            "INSERT INTO organization_memberships (id,organization_id,user_id,role,active) VALUES (:id,:org,:user,'DRIVER',true)"
        ),
        {"id": uuid.uuid4(), "org": juan["organization"]["id"], "user": pedro_id},
    )
    await admin_db.commit()
    # Juan owns Trip A; Pedro owns Trip B.
    trip_a = await finish(client, await create_trip(client, rows), stop="finish_unloading")
    attempt, photo, signature, pod = await successful(client, trip_a)
    driver_b = await create(
        client,
        "drivers",
        {
            **DATA["drivers"],
            "employee_number": "DRV-B",
            "license_number": None,
            "user_id": str(pedro_id),
            "first_name": "Pedro",
            "last_name": "Reyes",
        },
    )
    vehicle_b = await create(
        client, "vehicles", {**DATA["vehicles"], "unit_number": "TRK-B", "plate_number": "BBB-123"}
    )
    trip_b = await create_trip(client, {**rows, "drivers": driver_b, "vehicles": vehicle_b})
    await client.post("/api/v1/auth/logout")
    await login(client, "pedro@example.com")
    assert (await client.get(f"/api/v1/driver/trips/{trip_b['id']}")).status_code == 200
    for path in (
        f"/trips/{trip_a['id']}/delivery-attempts",
        f"/delivery-attempts/{attempt['attempt']['id']}",
        f"/pod/{pod['pod']['id']}",
        f"/evidence/{photo['evidence']['id']}",
        f"/evidence/{photo['evidence']['id']}/metadata",
        f"/evidence/{signature['evidence']['id']}",
    ):
        assert (await client.get("/api/v1" + path)).status_code == 404
    assert (
        await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/exception",
            json={
                "expected_version": pod["trip"]["version"],
                "exception_type": "OTHER",
                "notes": "Forbidden",
            },
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/pod/{pod['pod']['id']}/review",
            json={"expected_version": pod["trip"]["version"]},
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod",
            json=pod_body(pod["trip"]["version"]),
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
            params={
                "expected_version": pod["trip"]["version"],
                "filename": "replacement.png",
                "supersedes_id": photo["evidence"]["id"],
            },
            content=image_bytes(),
            headers={"Content-Type": "image/png"},
        )
    ).status_code == 404
    async with Session() as db:
        await set_context(db, str(pedro_id), juan["organization"]["id"])
        for table in (
            "delivery_attempts",
            "delivery_evidence",
            "proof_of_delivery",
            "delivery_exceptions",
        ):
            assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        await db.rollback()


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("OWNER", True),
        ("ADMIN", True),
        ("MANAGER", True),
        ("DISPATCHER", True),
        ("ACCOUNTING", False),
        ("MAINTENANCE", False),
    ],
)
async def test_delivery_role_matrix(client, admin_db, role, allowed):
    _, trip = await setup(client)
    identity = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text("UPDATE organization_memberships SET role=:role WHERE id=:id"),
        {"role": role, "id": identity["membership"]["id"]},
    )
    await admin_db.commit()
    assert (await client.get(f"/api/v1/trips/{trip['id']}/delivery-attempts")).status_code == (
        200 if allowed else 403
    )
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/delivery-attempts",
            json={"expected_version": trip["version"]},
        )
    ).status_code == (201 if allowed else 403)


async def test_other_notes_duplicate_attempt_and_bare_delivery_rejected(client):
    _, trip = await setup(client)
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/transition",
            json={"expected_version": trip["version"], "action": "deliver"},
        )
    ).status_code == 409
    attempt = await start(client, trip)
    assert (
        await client.post(
            f"/api/v1/trips/{trip['id']}/delivery-attempts",
            json={"expected_version": attempt["trip_version"]},
        )
    ).status_code == 409
    response = await client.post(
        f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/exception",
        json={"expected_version": attempt["trip_version"], "exception_type": "OTHER"},
    )
    assert response.status_code == 422
    results = await asyncio.gather(
        *(
            client.post(
                f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/exception",
                json={
                    "expected_version": attempt["trip_version"],
                    "exception_type": "RECIPIENT_UNAVAILABLE",
                },
            )
            for _ in range(2)
        )
    )
    assert sorted(row.status_code for row in results) == [201, 409]


async def test_concurrent_uploads_refresh_version_after_lock(client):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    responses = await asyncio.gather(
        *(
            client.post(
                f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
                params={
                    "expected_version": attempt["trip_version"],
                    "filename": f"photo-{index}.png",
                },
                content=image_bytes(),
                headers={"Content-Type": "image/png"},
            )
            for index in range(2)
        )
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert (
        len(
            (await client.get(f"/api/v1/delivery-attempts/{attempt['attempt']['id']}")).json()[
                "evidence"
            ]
        )
        == 1
    )


async def test_missing_or_corrupt_objects_cannot_confirm_delivery(client, admin_db):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    photo = await upload(client, attempt["attempt"]["id"], attempt["trip_version"])
    key = await admin_db.scalar(
        text("SELECT storage_key FROM delivery_evidence WHERE id=:id"),
        {"id": photo["evidence"]["id"]},
    )
    path = storage().path(key)
    original = path.read_bytes()
    try:
        path.write_bytes(b"corrupt object")
        assert (await client.get("/api/v1/evidence/" + photo["evidence"]["id"])).status_code == 503
        assert (
            await client.post(
                f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod",
                json=pod_body(photo["trip_version"]),
            )
        ).status_code == 409
        path.unlink()
        assert (await client.get("/api/v1/evidence/" + photo["evidence"]["id"])).status_code == 404
        assert (
            await client.post(
                f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod",
                json=pod_body(photo["trip_version"]),
            )
        ).status_code == 409
    finally:
        path.write_bytes(original)
    assert (await client.get(f"/api/v1/trips/{trip['id']}")).json()[
        "current_status"
    ] == "IN_TRANSIT"


async def test_denied_evidence_capabilities_and_csrf(client, admin_db):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    photo = await upload(client, attempt["attempt"]["id"], attempt["trip_version"])
    identity = (await client.get("/api/v1/me")).json()
    await admin_db.execute(
        text(
            "UPDATE organization_memberships SET permissions_json=jsonb_build_object('deny',jsonb_build_array('delivery_evidence.read','delivery_evidence.upload','pod.submit')) WHERE id=:id"
        ),
        {"id": identity["membership"]["id"]},
    )
    await admin_db.commit()
    assert (await client.get("/api/v1/evidence/" + photo["evidence"]["id"])).status_code == 403
    assert (await client.get(f"/api/v1/delivery-attempts/{attempt['attempt']['id']}")).json()[
        "evidence"
    ] == []
    assert (
        await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
            params={"expected_version": photo["trip_version"], "filename": "denied.png"},
            content=image_bytes(),
            headers={"Content-Type": "image/png"},
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod",
            json=pod_body(photo["trip_version"]),
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/exception",
            json={
                "expected_version": photo["trip_version"],
                "exception_type": "OTHER",
                "notes": "CSRF attack",
            },
            headers={"Origin": "https://attacker.invalid"},
        )
    ).status_code == 403


async def test_database_rejects_unbacked_pod_and_history_rewrite(client, admin_db):
    _, trip = await setup(client)
    attempt = await start(client, trip)
    with pytest.raises(DBAPIError, match="Delivery requires POD"):
        await admin_db.execute(
            text(
                "UPDATE trips SET current_status='DELIVERED', current_milestone='DELIVERED' WHERE id=:id"
            ),
            {"id": trip["id"]},
        )
    await admin_db.rollback()
    with pytest.raises(DBAPIError, match="POD policy cannot be bypassed"):
        await admin_db.execute(
            text("UPDATE trips SET pod_required=false WHERE id=:id"), {"id": trip["id"]}
        )
    await admin_db.rollback()
    with pytest.raises(DBAPIError, match="Successful attempt requires POD"):
        await admin_db.execute(
            text(
                "UPDATE delivery_attempts SET status='DELIVERED',completed_at=clock_timestamp() WHERE id=:id"
            ),
            {"id": attempt["attempt"]["id"]},
        )
        await admin_db.commit()
    await admin_db.rollback()
    photo = await upload(client, attempt["attempt"]["id"], attempt["trip_version"])
    with pytest.raises(DBAPIError, match="Evidence is immutable"):
        await admin_db.execute(
            text("UPDATE delivery_evidence SET storage_key='other' WHERE id=:id"),
            {"id": photo["evidence"]["id"]},
        )
    await admin_db.rollback()


async def test_pod_stage_and_closed_attempt_protection(client):
    _, trip = await setup(client, stop="arrive_delivery")
    attempt = await start(client, trip)
    photo = await upload(client, attempt["attempt"]["id"], attempt["trip_version"])
    path = f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod"
    assert (await client.post(path, json=pod_body(photo["trip_version"]))).status_code == 409
    trip = (await client.get(f"/api/v1/trips/{trip['id']}")).json()
    trip = await act(client, trip, "start_unloading")
    trip = await act(client, trip, "finish_unloading")
    delivered = await client.post(path, json=pod_body(trip["version"]))
    assert delivered.status_code == 201
    trip = delivered.json()["trip"]
    assert (await client.post(path, json=pod_body(trip["version"]))).status_code == 409
    trip = await review_delivery(client, trip)
    completed = await client.post(
        f"/api/v1/trips/{trip['id']}/complete",
        json={"expected_version": trip["version"], "closeout_reviewed": True},
    )
    assert completed.status_code == 200
    assert (await client.post(path, json=pod_body(completed.json()["version"]))).status_code == 409
