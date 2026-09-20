"""Create isolated local verification infrastructure; never connects to the user's database."""

import json
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".runtime" / "batch16"
RUN.mkdir(parents=True, exist_ok=True)
DB = "fleetpilot-mvp1-db"
VERIFY = "fleetpilot-mvp1-verify"
NETWORK = "fleetpilot-mvp1-local"
VOLUME = "fleetpilot-mvp1-pg"


def call(args, **kwargs):
    return subprocess.run(
        args, check=True, capture_output=True, text=True, **kwargs
    ).stdout.strip()


def main():
    if os.name == "nt" or str(ROOT) != "/home/user/projects/fleetpilot":
        raise SystemExit("Use the authoritative WSL repository")
    if shutil.disk_usage("/mnt/c").free < 1000000000:
        raise SystemExit("Stop: less than 1 GB host reserve")
    if subprocess.run(["docker", "inspect", DB], capture_output=True, check=False).returncode == 0:
        raise SystemExit("Isolated database already exists; inspect it, do not reset")
    owner = secrets.token_urlsafe(30)
    runtime = secrets.token_urlsafe(30)
    demo = secrets.token_urlsafe(24)
    postgres_env = RUN / "postgres.env"
    postgres_env.write_text(f"POSTGRES_PASSWORD={owner}\nPOSTGRES_DB=fleetpilot_test\n")
    postgres_env.chmod(0o600)
    for name, database, environment in [
        ("test", "fleetpilot_test", "test"),
        ("demo", "fleetpilot_demo", "development"),
    ]:
        text = (
            f"DATABASE_URL=postgresql+asyncpg://fleetpilot_app:{runtime}@{DB}:5432/{database}\n"
            f"ENVIRONMENT={environment}\nWEB_ORIGIN=http://localhost:3500\n"
            f"DEMO_PASSWORD={demo}\nLOGIN_LIMIT=100\nPYTHONDONTWRITEBYTECODE=1\n"
        )
        if name == "test":
            text += f"MIGRATION_DATABASE_URL=postgresql+asyncpg://postgres:{owner}@{DB}:5432/{database}\n"
        path = RUN / f"{name}-container.env"
        path.write_text(text)
        path.chmod(0o600)
    call(
        [
            "docker",
            "network",
            "create",
            "--label",
            "habi.scope=fleetpilot-mvp1",
            NETWORK,
        ]
    )
    call(
        ["docker", "volume", "create", "--label", "habi.scope=fleetpilot-mvp1", VOLUME]
    )
    call(
        [
            "docker",
            "run",
            "-d",
            "--pull=never",
            "--name",
            DB,
            "--network",
            NETWORK,
            "--label",
            "habi.scope=fleetpilot-mvp1",
            "--env-file",
            str(postgres_env),
            "--mount",
            f"type=volume,source={VOLUME},target=/var/lib/postgresql",
            "postgres:18.4",
        ]
    )
    ready = False
    for _ in range(40):
        result = subprocess.run(
            ["docker", "exec", DB, "pg_isready", "-U", "postgres"], capture_output=True, check=False
        )
        if result.returncode == 0:
            ready = True
            break
        time.sleep(0.5)
    if not ready:
        raise SystemExit("Isolated PostgreSQL did not become ready")
    sql = (
        f"CREATE ROLE fleetpilot_app LOGIN PASSWORD '{runtime}' NOSUPERUSER NOBYPASSRLS;\n"
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC;\n"
        "GRANT USAGE ON SCHEMA public TO fleetpilot_app;\n"
        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO fleetpilot_app;\n"
        "CREATE DATABASE fleetpilot_demo;\n"
    )
    call(
        [
            "docker",
            "exec",
            "-i",
            DB,
            "psql",
            "-U",
            "postgres",
            "-d",
            "fleetpilot_test",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input=sql,
    )
    call(
        [
            "docker",
            "run",
            "-d",
            "--pull=never",
            "--name",
            VERIFY,
            "--network",
            NETWORK,
            "--label",
            "habi.scope=fleetpilot-mvp1",
            "--env-file",
            str(RUN / "test-container.env"),
            "-v",
            f"{ROOT}:/workspace",
            "-w",
            "/workspace/apps/api",
            "fleetpilot-api:batch15-review",
            "sleep",
            "infinity",
        ]
    )
    print(
        json.dumps(
            {
                "database_container": DB,
                "verification_container": VERIFY,
                "source": str(ROOT),
                "source_database_changed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
