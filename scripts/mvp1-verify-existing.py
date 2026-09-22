"""Verify WSL sources with the existing Windows isolated test runtime, without provisioning."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = Path(r"C:\Users\User\Documents\ChatGPT\FleetPilot")
RUN = ROOT / ".runtime" / "batch16"


async def identity(env):
    connection = await asyncpg.connect(
        env["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    )
    try:
        row = await connection.fetchrow(
            "SELECT current_database() AS database, current_user AS role, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
        if (
            row["database"] != "fleetpilot_test"
            or row["rolsuper"]
            or row["rolbypassrls"]
        ):
            raise RuntimeError("Unsafe isolated test database identity")
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        print(
            json.dumps({**dict(row), "migration": revision, "source": str(ROOT)}),
            flush=True,
        )
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("tests", nargs="+")
    args = parser.parse_args()
    if os.name != "nt" or "wsl.localhost" not in str(ROOT).lower():
        raise SystemExit(
            "This explicit fallback uses WSL source through the existing Windows runtime"
        )
    env = dict(os.environ)
    env.update(
        {
            k: v
            for k, v in dotenv_values(WINDOWS / ".runtime" / "test.env").items()
            if v is not None
        }
    )
    for key in ("DATABASE_URL", "MIGRATION_DATABASE_URL"):
        u = urlparse(env[key])
        if u.hostname != "127.0.0.1" or u.port != 54329 or u.path != "/fleetpilot_test":
            raise SystemExit("Refusing a non-isolated existing test configuration")
    if env.get("ENVIRONMENT") != "test":
        raise SystemExit("Explicit test environment required")
    RUN.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(ROOT / "apps" / "api"),
        }
    )
    temporary = WINDOWS / ".runtime" / "batch16-pytest-temp"
    temporary.mkdir(parents=True, exist_ok=True)
    env.update({"TMP": str(temporary), "TEMP": str(temporary), "TMPDIR": str(temporary)})
    lock = WINDOWS / ".runtime" / "test-run.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, f"{os.getpid()} {time.time_ns()}\n".encode())
        asyncio.run(identity(env))
        code = subprocess.call(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                *args.tests,
                "--junitxml=" + str(RUN / (args.label + ".xml")),
            ],
            cwd=ROOT / "apps" / "api",
            env=env,
        )
        raise SystemExit(code)
    finally:
        os.close(fd)
        lock.unlink()


if __name__ == "__main__":
    main()
