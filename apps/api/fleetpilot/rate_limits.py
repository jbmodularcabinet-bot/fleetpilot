"""Shared, atomic fixed-window limits; memory mode is development/test only."""

import hashlib
import time
from collections import OrderedDict

from sqlalchemy import text

from .db import engine

login_windows = OrderedDict()
other_windows = OrderedDict()


async def consume(category: str, identity: str, limit: int, backend: str) -> bool:
    if backend == "postgres":
        digest = hashlib.sha256(f"{category}:{identity}".encode()).hexdigest()
        async with engine.begin() as db:
            count = await db.scalar(
                text("""
                INSERT INTO request_rate_windows(key_hash, expires_at, request_count)
                VALUES (:key, clock_timestamp() + interval '60 seconds', 1)
                ON CONFLICT (key_hash) DO UPDATE SET
                  request_count = CASE WHEN request_rate_windows.expires_at <= clock_timestamp()
                    THEN 1 ELSE LEAST(request_rate_windows.request_count + 1, :ceiling) END,
                  expires_at = CASE WHEN request_rate_windows.expires_at <= clock_timestamp()
                    THEN clock_timestamp() + interval '60 seconds' ELSE request_rate_windows.expires_at END
                RETURNING request_count
            """),
                {"key": digest, "ceiling": limit + 1},
            )
            # Bounded opportunistic expiry cleanup; no raw IP/session values are retained.
            await db.execute(
                text("""DELETE FROM request_rate_windows WHERE key_hash IN
                (SELECT key_hash FROM request_rate_windows WHERE expires_at < clock_timestamp()
                 LIMIT 100)""")
            )
        return count <= limit
    windows = login_windows if category == "auth" else other_windows
    key = identity if category == "auth" else f"{category}:{identity}"
    now = time.monotonic()
    since, count = windows.get(key, (now, 0))
    if now - since > 60:
        since, count = now, 0
    windows[key] = since, count + 1
    windows.move_to_end(key)
    if len(windows) > 10000:
        windows.popitem(last=False)
    return count < limit


def category_for(method, path, settings):
    if path.startswith("/api/v1/auth/") and method == "POST":
        return "auth", settings.login_limit
    if path.startswith(("/api/v1/evidence/", "/api/v1/expense-evidence/")) and method == "GET":
        return "evidence", settings.evidence_access_limit
    if method not in {"GET", "HEAD", "OPTIONS"}:
        if path.startswith(
            ("/api/v1/delivery-attempts/", "/api/v1/driver/sync/", "/api/v1/expenses/")
        ) and path.endswith("/evidence"):
            return "upload", settings.upload_limit
        return "mutation", settings.mutation_limit
    return None
