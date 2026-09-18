import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from botocore.exceptions import EndpointConnectionError, ReadTimeoutError
from pydantic import ValidationError
from sqlalchemy import text

from fleetpilot.config import Settings, get_settings
from fleetpilot.evidence_storage import LocalEvidenceStorage
from fleetpilot.main import settings
from fleetpilot.rate_limits import consume
from fleetpilot.s3_storage import S3EvidenceStorage
from fleetpilot.storage_admin import reconcile, restore_objects, snapshot

from . import test_delivery as delivery
from .delivery_helpers import image_bytes, upload


@pytest.fixture
def s3_store(monkeypatch):
    path = Path(__file__).resolve().parents[3] / ".runtime/s3-test.json"
    if not path.exists():
        pytest.skip("Real local S3 gateway credentials not provisioned; integration UNVERIFIED")
    creds = json.loads(path.read_text())
    cfg = get_settings().model_copy(
        update={
            "storage_backend": "s3",
            "s3_endpoint": "http://127.0.0.1:9000",
            "s3_bucket": "fp-test-" + uuid.uuid4().hex,
            "s3_access_key": creds["access"],
            "s3_secret_key": creds["secret"],
        }
    )
    store = S3EvidenceStorage(cfg)
    store.client.create_bucket(Bucket=store.bucket)
    monkeypatch.setattr("fleetpilot.delivery_routes.storage", lambda: store)
    yield store
    # Explicit disposable bucket cleanup; never points to configured application bucket.
    assert store.bucket.startswith("fp-test-")
    for key in list(store.keys()):
        store.discard_uncommitted(key)
    store.client.delete_bucket(Bucket=store.bucket)


def test_real_s3_private_immutable_integrity_and_restore(s3_store, tmp_path):
    key = f"{uuid.uuid4().hex}/{uuid.uuid4().hex}.png"
    data = image_bytes()
    s3_store.put(key, data)
    assert s3_store.head(key) == len(data)
    assert s3_store.read(key) == data
    with pytest.raises(FileExistsError):
        s3_store.put(key, b"replacement")
    response = httpx.get(f"http://127.0.0.1:9000/{s3_store.bucket}/{key}")
    assert response.status_code in {401, 403}
    with pytest.raises(ValueError):
        s3_store.read("../outside")
    rows = [
        {
            "id": uuid.uuid4(),
            "storage_key": key,
            "checksum": hashlib.sha256(data).hexdigest(),
            "status": "ACTIVE",
        }
    ]
    assert not any(reconcile(rows, s3_store).values())
    snapshot(rows, s3_store, tmp_path / "snapshot")
    s3_store.discard_uncommitted(key)
    assert reconcile(rows, s3_store)["missing"]
    restore_objects(tmp_path / "snapshot", s3_store)
    assert s3_store.read(key) == data
    rows[0]["checksum"] = "0" * 64
    assert reconcile(rows, s3_store)["checksum_mismatch"]
    assert reconcile([], s3_store)["orphan"]
    s3_store.health_check()
    assert list(s3_store.keys()) == [key]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "test_successful_delivery_golden_and_review",
        "test_failed_retry_golden_preserves_original",
        "test_cross_tenant_and_direct_postgres_rls",
        "test_same_tenant_other_driver_evidence_boundary",
    ],
)
async def test_real_s3_existing_workflows(client, admin_db, s3_store, scenario):
    await getattr(delivery, scenario)(client, admin_db)


@pytest.mark.asyncio
async def test_s3_outage_timeout_missing_and_compensation(client, admin_db, s3_store, monkeypatch):
    _, trip = await delivery.setup(client)
    attempt = await delivery.start(client, trip)
    original = s3_store.client.put_object
    for failure in [
        EndpointConnectionError(endpoint_url="https://private.invalid"),
        ReadTimeoutError(endpoint_url="https://private.invalid"),
    ]:

        def fail(failure=failure, **kwargs):
            raise failure

        monkeypatch.setattr(s3_store.client, "put_object", fail)
        response = await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
            params={"expected_version": attempt["trip_version"], "filename": "photo.png"},
            content=image_bytes(),
            headers={"Content-Type": "image/png"},
        )
        assert response.status_code == 503
        assert not list(s3_store.keys())
    monkeypatch.setattr(s3_store.client, "put_object", original)
    photo = await upload(client, attempt["attempt"]["id"], attempt["trip_version"])
    evidence_url = "/api/v1/evidence/" + photo["evidence"]["id"]

    def read_failure(**kwargs):
        raise EndpointConnectionError(endpoint_url="https://secret.invalid")

    with monkeypatch.context() as patch:
        patch.setattr(s3_store.client, "get_object", read_failure)
        response = await client.get(evidence_url)
        assert response.status_code == 503 and "secret.invalid" not in response.text
    key = next(s3_store.keys())
    s3_store.discard_uncommitted(key)
    assert (await client.get(evidence_url)).status_code == 404
    response = await client.post(
        f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/pod",
        json=delivery.pod_body(photo["trip_version"]),
    )
    assert response.status_code == 409
    assert (await client.get(f"/api/v1/trips/{trip['id']}")).json()[
        "current_status"
    ] == "IN_TRANSIT"


@pytest.mark.asyncio
async def test_shared_rate_limit_concurrency_expiry(client, admin_db):
    key = uuid.uuid4().hex
    results = await asyncio.gather(*(consume("test", key, 3, "postgres") for _ in range(10)))
    assert sum(results) == 3
    await admin_db.execute(
        text("UPDATE request_rate_windows SET expires_at=now()-interval '1 minute'")
    )
    await admin_db.commit()
    assert await consume("test", key, 3, "postgres")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,method,field",
    [
        ("/api/v1/auth/login", "POST", "login_limit"),
        (f"/api/v1/delivery-attempts/{uuid.uuid4()}/evidence", "POST", "upload_limit"),
        (f"/api/v1/evidence/{uuid.uuid4()}", "GET", "evidence_access_limit"),
        (f"/api/v1/delivery-attempts/{uuid.uuid4()}/pod", "POST", "mutation_limit"),
        (f"/api/v1/delivery-attempts/{uuid.uuid4()}/exception", "POST", "mutation_limit"),
    ],
)
async def test_shared_endpoint_limits_and_headers(
    client, admin_db, monkeypatch, path, method, field
):
    await admin_db.execute(text("TRUNCATE request_rate_windows"))
    await admin_db.commit()
    monkeypatch.setattr(settings, "rate_limit_backend", "postgres")
    monkeypatch.setattr(settings, field, 1)
    assert (await client.request(method, path)).status_code != 429
    response = await client.request(method, path)
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in response.headers["content-security-policy"]


@pytest.mark.asyncio
async def test_chunked_limits_and_failure_headers(client):
    async def chunks():
        for _ in range(10):
            yield b"x" * 8192

    response = await client.post("/api/v1/auth/login", content=chunks())
    assert response.status_code == 413
    assert response.headers["x-request-id"]
    assert (
        await client.post("/api/v1/auth/login", headers={"Origin": "https://evil.invalid"})
    ).status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"storage_backend": "local"},
        {"rate_limit_backend": "memory"},
        {"web_origin": "http://fleet.example"},
        {"web_origin": "https://*.example"},
        {"s3_bucket": None},
        {"s3_endpoint": "http://public.example"},
        {"s3_access_key": "only-one"},
    ],
)
def test_production_configuration_fail_closed(changes):
    cfg = dict(
        environment="production",
        database_url="postgresql+asyncpg://app:long-random-fixture@localhost/db",
        web_origin="https://fleet.example",
        storage_backend="s3",
        s3_bucket="private-evidence",
        rate_limit_backend="postgres",
    )
    with pytest.raises((ValidationError, RuntimeError)):
        Settings(**{**cfg, **changes}, _env_file=None).validate_runtime()


def test_local_storage_snapshot_integrity(tmp_path):
    store = LocalEvidenceStorage(tmp_path / "local")
    store.health_check()
    assert list(store.keys()) == []
    with pytest.raises(ValueError):
        store.put("../escape.png", b"x")
    key = f"{uuid.uuid4().hex}/{uuid.uuid4().hex}.png"
    store.put(key, b"x" * (5 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="size limit"):
        store.read(key)


def test_production_secrets_and_validation_output():
    cfg = dict(
        environment="production",
        web_origin="https://fleet.example",
        storage_backend="s3",
        s3_bucket="private-evidence",
        rate_limit_backend="postgres",
    )
    for password in ["", "replace-this-private-secret"]:
        with pytest.raises(RuntimeError):
            Settings(
                **cfg,
                database_url=f"postgresql+asyncpg://app:{password}@localhost/db",
                _env_file=None,
            ).validate_runtime()
    with pytest.raises(ValidationError) as caught:
        Settings(
            **{**cfg, "web_origin": "*"},
            database_url="postgresql+asyncpg://app:do-not-print-this-secret@localhost/db",
            _env_file=None,
        )
    assert "do-not-print-this-secret" not in str(caught.value)


def test_monitoring_allowlist_does_not_export_secrets(monkeypatch):
    from fleetpilot import hardening

    captured = []
    monkeypatch.setattr(hardening, "monitor", captured.append)
    hardening.emit(
        "request.failed",
        request_id="safe",
        password="secret",
        authorization="token",
        signed_url="private",
    )
    assert captured[0]["request_id"] == "safe"
    assert "secret" not in json.dumps(captured) and "token" not in json.dumps(captured)


@pytest.mark.asyncio
async def test_two_processes_share_rate_budget():
    key = uuid.uuid4().hex
    code = f"""import asyncio,json
from fleetpilot.rate_limits import consume
from fleetpilot.db import engine
async def main():
    results=[await consume('process-test', '{key}', 3, 'postgres') for _ in range(3)]
    await engine.dispose()
    print(json.dumps(results))
asyncio.run(main())
"""

    async def worker():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        assert process.returncode == 0, stderr.decode()
        return json.loads(stdout)

    results = await asyncio.gather(worker(), worker())
    assert sum(sum(result) for result in results) == 3


def test_public_bucket_policy_fails_readiness(s3_store, monkeypatch):
    monkeypatch.setattr(
        s3_store.client,
        "get_bucket_policy",
        lambda **kwargs: {
            "Policy": json.dumps({"Statement": [{"Effect": "Allow", "Principal": "*"}]})
        },
    )
    with pytest.raises(OSError, match="Public bucket"):
        s3_store.health_check()


@pytest.mark.asyncio
async def test_s3_db_failure_compensates_private_object(client, admin_db, s3_store):
    _, trip = await delivery.setup(client)
    attempt = await delivery.start(client, trip)
    await admin_db.execute(
        text(
            "CREATE FUNCTION reject_s3_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='evidence.uploaded' THEN RAISE EXCEPTION 'synthetic failure'; END IF; RETURN NEW; END $$"
        )
    )
    await admin_db.execute(
        text(
            "CREATE TRIGGER reject_s3_audit BEFORE INSERT ON audit_logs FOR EACH ROW EXECUTE FUNCTION reject_s3_audit()"
        )
    )
    await admin_db.commit()
    try:
        response = await client.post(
            f"/api/v1/delivery-attempts/{attempt['attempt']['id']}/evidence",
            params={"expected_version": attempt["trip_version"], "filename": "photo.png"},
            content=image_bytes(),
            headers={"Content-Type": "image/png"},
        )
        assert response.status_code == 500
        assert not list(s3_store.keys())
        assert not (
            await client.get(f"/api/v1/delivery-attempts/{attempt['attempt']['id']}")
        ).json()["evidence"]
    finally:
        await admin_db.execute(text("DROP TRIGGER reject_s3_audit ON audit_logs"))
        await admin_db.execute(text("DROP FUNCTION reject_s3_audit()"))
        await admin_db.commit()


@pytest.mark.asyncio
async def test_liveness_independent_of_storage_readiness(client, monkeypatch):
    def unavailable():
        raise OSError("private provider location must not escape")

    monkeypatch.setattr("fleetpilot.main.storage", unavailable)
    assert (await client.get("/health")).status_code == 200
    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


@pytest.mark.asyncio
async def test_limiter_outage_fails_closed(client, monkeypatch):
    async def unavailable(*args):
        raise OSError("secret connection")

    monkeypatch.setattr("fleetpilot.main.consume", unavailable)
    response = await client.post("/api/v1/auth/login")
    assert response.status_code == 503 and "secret" not in response.text
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.asyncio
async def test_upload_authorization_precedes_consuming_chunked_body(client):
    consumed = []

    async def body():
        consumed.append(True)
        yield image_bytes()

    response = await client.post(
        f"/api/v1/delivery-attempts/{uuid.uuid4()}/evidence",
        params={"expected_version": 1, "filename": "private.png"},
        content=body(),
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code == 401
    assert not consumed
