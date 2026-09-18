"""Run API tasks from the repo root, with an explicit development/test env file."""

import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
args = sys.argv[1:]
test = "--test" in args
if test:
    args.remove("--test")
env = dict(os.environ)
env.update(
    {
        key: value
        for key, value in dotenv_values(
            root / (".runtime/test.env" if test else ".env")
        ).items()
        if value is not None
    }
)
for key in ("WEB_ORIGIN", "LOGIN_LIMIT"):
    if key in os.environ:
        env[key] = os.environ[key]
lock_path = root / ".runtime" / "test-run.lock"
lock_fd = None
if test:
    # Test helpers and seed() read DEMO_PASSWORD from os.environ in this process.
    # Keep it identical to the isolated test.env value instead of inheriting a
    # development-shell password that may differ from the test database seed.
    os.environ["DEMO_PASSWORD"] = env.get("DEMO_PASSWORD", "")
    if not env.get("DATABASE_URL", "").endswith("/fleetpilot_test"):
        raise SystemExit("Refusing tests outside the isolated fleetpilot_test database")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Keep pytest temporary files inside the repository runtime area. The
    # sandboxed engineering process may not have access to another process's
    # system-level pytest temp directory on Windows.
    pytest_tmp = root / ".runtime" / "pytest-tmp"
    pytest_tmp.mkdir(parents=True, exist_ok=True)
    env["TMP"] = str(pytest_tmp)
    env["TEMP"] = str(pytest_tmp)
    env["TMPDIR"] = str(pytest_tmp)
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, f"{os.getpid()} {time.time_ns()}\n".encode())
    except FileExistsError:
        raise SystemExit(
            "Another FleetPilot --test task owns fleetpilot_test. Wait for it to finish; "
            f"if no test process exists, remove stale lock: {lock_path}"
        )
try:
    raise SystemExit(
        subprocess.call([sys.executable, "-m", *args], cwd=root / "apps/api", env=env)
    )
finally:
    if lock_fd is not None:
        os.close(lock_fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
