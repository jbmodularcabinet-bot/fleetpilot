from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .router import ProviderRouter
from .store import CreativeOSStore, now_iso

TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED"}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationQueueService:
    def __init__(self, store: CreativeOSStore):
        self.store = store

    def enqueue(self, generation_job_id: str, priority: int = 100,
                max_attempts: int = 3, available_at: str | None = None) -> dict[str, Any]:
        self.store.get("generation_jobs", generation_job_id)
        existing = self.store.list("generation_queue", {"generation_job_id": generation_job_id})
        if existing:
            return existing[0]
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        stamp = now_iso()
        return self.store.create("generation_queue", {
            "generation_job_id": generation_job_id,
            "state": "QUEUED",
            "priority": int(priority),
            "available_at": available_at or stamp,
            "attempt_count": 0,
            "max_attempts": int(max_attempts),
        })

    def claim_next(self, worker_id: str, lease_seconds: int = 60,
                   now: datetime | None = None) -> dict[str, Any] | None:
        moment = now or _now()
        stamp = _iso(moment)
        token = secrets.token_urlsafe(24)
        lease = _iso(moment + timedelta(seconds=lease_seconds))
        conn = self.store.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("""
                SELECT * FROM generation_queue
                WHERE state='QUEUED' AND available_at<=?
                  AND cancel_requested_at IS NULL
                  AND attempt_count < max_attempts
                ORDER BY priority ASC, available_at ASC, created_at ASC, id ASC
                LIMIT 1
            """, (stamp,)).fetchone()
            if row is None:
                conn.commit()
                return None
            updated = conn.execute("""
                UPDATE generation_queue
                SET state='CLAIMED', claimed_by=?, claim_token=?, claimed_at=?,
                    lease_expires_at=?, updated_at=?
                WHERE id=? AND state='QUEUED' AND available_at<=?
            """, (worker_id, token, stamp, lease, stamp, row["id"], stamp))
            if updated.rowcount != 1:
                conn.rollback()
                return None
            conn.commit()
            return self.store.get("generation_queue", row["id"])
        except Exception:
            conn.rollback()
            raise

    def start(self, queue_id: str, claim_token: str) -> dict[str, Any]:
        stamp = now_iso()
        row = self.store.get("generation_queue", queue_id)
        if row["state"] != "CLAIMED" or row["claim_token"] != claim_token:
            raise ValueError("invalid queue claim")
        if row["cancel_requested_at"]:
            return self._cancel_claimed(queue_id, claim_token)
        if int(row["attempt_count"]) >= int(row["max_attempts"]):
            return self._finish(queue_id, "FAILED", "MAX_ATTEMPTS", "retry limit reached")
        cur = self.store.conn.execute("""
            UPDATE generation_queue
            SET state='RUNNING', attempt_count=attempt_count+1,
                started_at=COALESCE(started_at, ?), updated_at=?
            WHERE id=? AND state='CLAIMED' AND claim_token=?
        """, (stamp, stamp, queue_id, claim_token))
        if cur.rowcount != 1:
            self.store.conn.rollback()
            raise ValueError("claim lost before execution")
        self.store.conn.commit()
        return self.store.get("generation_queue", queue_id)

    def request_cancel(self, queue_id: str) -> dict[str, Any]:
        row = self.store.get("generation_queue", queue_id)
        if row["state"] in TERMINAL_STATES:
            return row
        stamp = now_iso()
        if row["state"] == "QUEUED":
            self.store.conn.execute("""
                UPDATE generation_queue SET state='CANCELLED', cancel_requested_at=?,
                    finished_at=?, updated_at=? WHERE id=? AND state='QUEUED'
            """, (stamp, stamp, stamp, queue_id))
        else:
            self.store.conn.execute("""
                UPDATE generation_queue SET cancel_requested_at=?, updated_at=? WHERE id=?
            """, (stamp, stamp, queue_id))
        self.store.conn.commit()
        return self.store.get("generation_queue", queue_id)

    def _cancel_claimed(self, queue_id: str, token: str) -> dict[str, Any]:
        stamp = now_iso()
        self.store.conn.execute("""
            UPDATE generation_queue SET state='CANCELLED', finished_at=?, updated_at=?
            WHERE id=? AND state='CLAIMED' AND claim_token=?
        """, (stamp, stamp, queue_id, token))
        self.store.conn.commit()
        return self.store.get("generation_queue", queue_id)

    def _finish(self, queue_id: str, state: str, code: str | None = None,
                message: str | None = None) -> dict[str, Any]:
        stamp = now_iso()
        self.store.conn.execute("""
            UPDATE generation_queue
            SET state=?, finished_at=?, last_error_code=?, last_error_message=?, updated_at=?
            WHERE id=?
        """, (state, stamp, code, message, stamp, queue_id))
        self.store.conn.commit()
        return self.store.get("generation_queue", queue_id)

    def fail_or_retry(self, queue_id: str, claim_token: str, code: str,
                      message: str, backoff_seconds: int = 0) -> dict[str, Any]:
        row = self.store.get("generation_queue", queue_id)
        if row["state"] != "RUNNING" or row["claim_token"] != claim_token:
            raise ValueError("invalid running claim")
        if int(row["attempt_count"]) >= int(row["max_attempts"]):
            return self._finish(queue_id, "FAILED", code, message)
        stamp = now_iso()
        available = _iso(_now() + timedelta(seconds=backoff_seconds))
        self.store.conn.execute("""
            UPDATE generation_queue
            SET state='QUEUED', available_at=?, claimed_by=NULL, claim_token=NULL,
                claimed_at=NULL, lease_expires_at=NULL, last_error_code=?,
                last_error_message=?, updated_at=? WHERE id=? AND claim_token=?
        """, (available, code, message, stamp, queue_id, claim_token))
        self.store.conn.commit()
        return self.store.get("generation_queue", queue_id)
    def recover_stale(self, now: datetime | None = None) -> list[dict[str, Any]]:
        stamp = _iso(now or _now())
        rows = self.store.conn.execute("""
            SELECT * FROM generation_queue
            WHERE state IN ('CLAIMED','RUNNING') AND lease_expires_at < ?
            ORDER BY created_at ASC, id ASC
        """, (stamp,)).fetchall()
        recovered: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            assets = self.store.list("generated_assets", {"generation_job_id": row["generation_job_id"]})
            if assets:
                recovered.append(self._finish(row["id"], "SUCCEEDED"))
            elif row["cancel_requested_at"]:
                recovered.append(self._finish(row["id"], "CANCELLED"))
            elif int(row["attempt_count"]) >= int(row["max_attempts"]):
                recovered.append(self._finish(row["id"], "FAILED", "LEASE_EXPIRED", "retry limit reached"))
            else:
                self.store.conn.execute("""
                    UPDATE generation_queue SET state='QUEUED', claimed_by=NULL,
                        claim_token=NULL, claimed_at=NULL, lease_expires_at=NULL,
                        last_error_code='LEASE_EXPIRED', last_error_message='stale worker recovered',
                        updated_at=? WHERE id=?
                """, (stamp, row["id"]))
                self.store.conn.commit()
                recovered.append(self.store.get("generation_queue", row["id"]))
        return recovered


class GenerationWorker:
    def __init__(self, store: CreativeOSStore, router: ProviderRouter, worker_id: str):
        self.store = store
        self.queue = GenerationQueueService(store)
        self.router = router
        self.worker_id = worker_id

    def run_once(self) -> dict[str, Any] | None:
        claimed = self.queue.claim_next(self.worker_id)
        if claimed is None:
            return None
        job = self.store.get("generation_jobs", claimed["generation_job_id"])
        existing = self.store.list("generated_assets", {"generation_job_id": job["id"]})
        if existing:
            self.queue._finish(claimed["id"], "SUCCEEDED")
            return existing[0]
        req = self.store.get("asset_requirements", job["asset_requirement_id"])
        scene = self.store.get("scenes", job["scene_id"])
        capability = str(req["asset_type"]).lower()
        try:
            provider = self.router.resolve(capability, job["provider"], bool(scene.get("immutable_ui")))
        except Exception as exc:
            self.queue._finish(claimed["id"], "FAILED", "ROUTING_ERROR", str(exc))
            return self.queue.store.get("generation_queue", claimed["id"])
        running = self.queue.start(claimed["id"], claimed["claim_token"])
        if running["state"] == "CANCELLED":
            return running
        self.store.update("generation_jobs", job["id"], {"state": "RUNNING", "error": None})
        try:
            result = provider.generate(job)
        except Exception as exc:
            self.store.update("generation_jobs", job["id"], {"state": "FAILED", "error": str(exc)})
            return self.queue.fail_or_retry(claimed["id"], claimed["claim_token"], "PROVIDER_ERROR", str(exc))
        fresh = self.store.get("generation_queue", claimed["id"])
        if fresh["cancel_requested_at"]:
            self.store.update("generation_jobs", job["id"], {
                "state": "CANCELLED", "response_json": result.metadata,
                "error": "cancelled after provider returned; output not accepted",
            })
            return self.queue._finish(claimed["id"], "CANCELLED", "CANCELLED_AFTER_RUN",
                                      "provider returned after cancellation; output rejected")
        checksum = hashlib.sha256(result.payload).hexdigest()
        asset = self.store.create("generated_assets", {
            "generation_job_id": job["id"], "asset_requirement_id": job["asset_requirement_id"],
            "output_path": result.output_path, "output_type": result.output_type,
            "output_metadata_json": result.metadata, "prompt_snapshot": job["prompt"],
            "provider_snapshot": job["provider_snapshot"], "model_snapshot": job["model_snapshot"],
            "checksum_sha256": checksum, "review_state": "PENDING",
        })
        self.store.update("generation_jobs", job["id"], {
            "state": "SUCCEEDED", "output_path": result.output_path,
            "response_json": result.metadata, "error": None,
        })
        self.queue._finish(claimed["id"], "SUCCEEDED")
        return asset
