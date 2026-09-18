"""Create isolated databases/buckets, run HTTPS delivery, dump, restore and verify.

Requires a real loopback S3 gateway (.runtime/s3-test.json), pg_dump/pg_restore
and the existing isolated test connection. Never drops or reuses databases.
Synthetic backup artifacts are private operational data under ignored .runtime.
"""

import asyncio
import datetime
import ipaddress
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps/api"
sys.path.insert(0, str(API))


def run(args, env, log):
    result = subprocess.run(args, env=env, cwd=API, stdout=log, stderr=log, check=False)
    if result.returncode:
        raise RuntimeError("Drill command failed; inspect private drill log")


def server(env, directory):
    log = (directory / "api.log").open("a")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "fleetpilot.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8446",
            "--no-access-log",
            "--ssl-keyfile",
            str(directory / "key.pem"),
            "--ssl-certfile",
            str(directory / "cert.pem"),
        ],
        cwd=API,
        env={**env, "MIGRATION_DATABASE_URL": ""},
        stdout=log,
        stderr=log,
    )
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(
                "Production-like API startup failed; inspect private log"
            )
        try:
            if (
                httpx.get(
                    "https://127.0.0.1:8446/ready", verify=False, timeout=2
                ).status_code
                == 200
            ):
                return process, log
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    process.terminate()
    raise RuntimeError("Readiness timeout")


async def main():
    suffix = uuid.uuid4().hex[:12]
    directory = (
        ROOT
        / ".runtime"
        / f"batch{12 if os.environ.get('DRILL_BATCH12') else 9 if os.environ.get('DRILL_BATCH9') else 6}-drill-{suffix}"
    )
    directory.mkdir()
    env = {**os.environ, **dotenv_values(ROOT / ".runtime/test.env")}
    source_url = env["MIGRATION_DATABASE_URL"]
    if not source_url.endswith("/fleetpilot_test"):
        raise RuntimeError("Drill requires isolated test configuration")
    parsed = urlparse(source_url)
    names = [f"fleetpilot_drill_{suffix}", f"fleetpilot_restore_{suffix}"]
    owner_base = source_url.rsplit("/", 1)[0]
    app_base = env["DATABASE_URL"].rsplit("/", 1)[0]
    admin = await asyncpg.connect(
        (owner_base + "/postgres").replace("postgresql+asyncpg", "postgresql")
    )
    for name in names:
        assert (
            name.startswith(("fleetpilot_drill_", "fleetpilot_restore_"))
            and name.replace("_", "").isalnum()
        )
        await admin.execute(f'CREATE DATABASE "{name}"')
    await admin.close()
    env.update(
        DATABASE_URL=app_base + "/" + names[0],
        MIGRATION_DATABASE_URL=owner_base + "/" + names[0],
        ENVIRONMENT="test",
    )
    db = await asyncpg.connect(
        env["MIGRATION_DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    )
    await db.execute(
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO fleetpilot_app; ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fleetpilot_app"
    )
    await db.close()
    log = (directory / "drill.log").open("w")
    run([sys.executable, "-m", "alembic", "upgrade", "head"], env, log)
    run([sys.executable, "-m", "fleetpilot.seed"], env, log)
    creds = json.loads((ROOT / ".runtime/s3-test.json").read_text())
    env.update(
        ENVIRONMENT="production",
        WEB_ORIGIN="https://localhost:8446",
        STORAGE_BACKEND="s3",
        S3_ENDPOINT="http://127.0.0.1:9000",
        S3_ALLOW_INSECURE_LOOPBACK="true",
        S3_BUCKET=f"fp-drill-{suffix}",
        S3_ACCESS_KEY=creds["access"],
        S3_SECRET_KEY=creds["secret"],
        RATE_LIMIT_BACKEND="postgres",
        LOGIN_LIMIT="100",
        DRILL_STATE=str(directory / "state.json"),
    )
    os.environ.update(env)
    from fleetpilot.config import get_settings
    from fleetpilot.s3_storage import S3EvidenceStorage
    from fleetpilot.storage_admin import reconcile, restore_objects, snapshot

    store = S3EvidenceStorage(get_settings())
    store.client.create_bucket(Bucket=store.bucket)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
        )
        .not_valid_after(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    (directory / "key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (directory / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    for restart in range(2):
        process, api_log = server(env, directory)
        try:
            run([sys.executable, "-m", "tests.hardening_workflow"], env, log)
        finally:
            process.terminate()
            process.wait(timeout=15)
            api_log.close()
    # Writers are stopped for the coherent DB/object snapshot.
    db = await asyncpg.connect(
        env["MIGRATION_DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    )
    rows = await db.fetch(
        "SELECT id, storage_key, checksum, status FROM delivery_evidence UNION ALL SELECT id,storage_key,checksum,status FROM expense_evidence UNION ALL SELECT id,storage_key,checksum,status FROM maintenance_evidence"
    )
    counts = {
        table: await db.fetchval(f"SELECT count(*) FROM {table}")
        for table in [
            "users",
            "organizations",
            "trips",
            "trip_milestones",
            "audit_logs",
            "delivery_attempts",
            "proof_of_delivery",
            "delivery_evidence",
            "trip_revenue",
            "revenue_effective_values",
            "cash_advances",
            "cash_advance_settlement_entries",
            "trip_financial_review_events",
            "trip_expenses",
            "expense_revisions",
            "expense_evidence",
            "closed_trip_adjustments",
            "expense_effective_values",
            "customers",
            "vehicles",
            "drivers",
            "maintenance_schedules",
            "maintenance_work_orders",
            "maintenance_cost_items",
            "driver_defects",
            "maintenance_evidence",
            "maintenance_events",
            "driver_sync_commands",
        ]
    }
    await db.close()
    assert not any(reconcile(rows, store).values())
    snapshot(rows, store, directory / "objects")
    pg_env = {
        **env,
        "PGHOST": parsed.hostname,
        "PGPORT": str(parsed.port),
        "PGUSER": parsed.username,
        "PGPASSWORD": parsed.password,
    }
    bin_dir = Path(
        os.environ.get(
            "PG_BIN", str(ROOT / ".runtime/tools/postgresql-client/pgsql/bin")
        )
    )
    ext = ".exe" if os.name == "nt" else ""
    dump = directory / "database.dump"
    run(
        [
            str(bin_dir / ("pg_dump" + ext)),
            "--format=custom",
            "--no-owner",
            "--file",
            str(dump),
            "--dbname",
            names[0],
        ],
        pg_env,
        log,
    )
    run(
        [
            str(bin_dir / ("pg_restore" + ext)),
            "--exit-on-error",
            "--no-owner",
            "--dbname",
            names[1],
            str(dump),
        ],
        pg_env,
        log,
    )
    restored = S3EvidenceStorage(
        get_settings().model_copy(update={"s3_bucket": f"fp-restore-{suffix}"})
    )
    restored.client.create_bucket(Bucket=restored.bucket)
    restore_objects(directory / "objects", restored)
    assert not any(reconcile(rows, restored).values())
    env.update(
        DATABASE_URL=app_base + "/" + names[1],
        MIGRATION_DATABASE_URL=owner_base + "/" + names[1],
        S3_BUCKET=restored.bucket,
    )
    run([sys.executable, "-m", "alembic", "upgrade", "head"], env, log)
    db = await asyncpg.connect(
        env["MIGRATION_DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    )
    for table, count in counts.items():
        assert await db.fetchval(f"SELECT count(*) FROM {table}") == count
    rls = await db.fetch(
        "SELECT relname,relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND relrowsecurity ORDER BY relname"
    )
    assert len(rls) == 31 and all(row["relforcerowsecurity"] for row in rls)
    # A snapshot can contain sessions revoked after backup; never revive them.
    await db.execute("DELETE FROM auth_sessions")
    assert await db.fetchval("SELECT count(*) FROM auth_sessions") == 0
    await db.close()
    process, api_log = server(env, directory)
    try:
        run([sys.executable, "-m", "tests.hardening_workflow"], env, log)
        if env.get("DRILL_BATCH9") == "1":
            run([sys.executable, "-m", "tests.verification_load"], env, log)
    finally:
        process.terminate()
        process.wait(timeout=15)
        api_log.close()
    log.close()
    report = {
        "golden": "PASS",
        "restart": "PASS",
        "restore": "PASS",
        "private_s3": "PASS",
        "reconciliation": "PASS",
        "restored_counts": counts,
        "restored_forced_rls_tables": len(rls),
        "remote_production": "UNVERIFIED",
    }
    (directory / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({**report, "artifacts": str(directory)}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
