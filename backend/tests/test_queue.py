import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.generation import GenerationService, MockGenerationResult
from creativeos_db.queue import GenerationQueueService, GenerationWorker
from creativeos_db.router import ProviderRegistration, ProviderRouter, default_router


class AlwaysFailProvider:
    name = "FAIL"
    def generate(self, job):
        raise RuntimeError("forced queue failure")


class CancelDuringRunProvider:
    name = "CANCEL"
    def __init__(self, store):
        self.store = store
    def generate(self, job):
        row = self.store.list("generation_queue", {"generation_job_id": job["id"]})[0]
        GenerationQueueService(self.store).request_cancel(row["id"])
        return MockGenerationResult("mock://cancelled", "mock", {"late": True}, b"late-output")

class Batch7QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "creativeos.sqlite3"
        self.store = CreativeOSStore(self.db)
        self.assertEqual(self.store.migrate_to_latest(), 7)
        brand = BrandBrainService(self.store).load_fleetpilot_fixture()
        campaign = self.store.create("campaigns", {"brand_profile_id": brand["id"], "title": "Queue"})
        board = self.store.create("storyboards", {"campaign_id": campaign["id"], "title": "Queue"})
        self.scene = self.store.create("scenes", {
            "storyboard_id": board["id"], "position": 1, "title": "Generate",
            "duration_seconds": 5, "scene_type": "AI_IMAGE", "generation_method": "GENERATIVE",
        })
        self.gen = GenerationService(self.store, default_router().resolve("image", "MOCK"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def make_job(self, asset_type="image", provider="MOCK"):
        req = self.gen.create_requirement(self.scene["id"], {"asset_type": asset_type, "purpose": "test"})
        return self.gen.create_job(req["id"], provider, "model-v1", f"make {asset_type}")

    def test_migration_v5_v6_rollback_reapply_preserves_job(self):
        job = self.make_job()
        job_id = job["id"]
        self.assertEqual(self.store.rollback_to(5), 5)
        self.assertEqual(self.store.get("generation_jobs", job_id)["id"], job_id)
        self.assertEqual(self.store.migrate_to_latest(), 7)
        self.assertEqual(self.store.get("generation_jobs", job_id)["id"], job_id)

    def test_router_capabilities_disabled_live_and_immutable_ui(self):
        router = default_router()
        for cap in ("image", "video", "presenter", "voice"):
            self.assertEqual(router.resolve(cap, "MOCK").name, "MOCK")
        with self.assertRaises(RuntimeError):
            router.resolve("image", "LIVE_IMAGE")
        with self.assertRaises(ValueError):
            router.resolve("video", "MOCK", immutable_ui=True)

    def test_atomic_claim_and_claim_token_enforcement(self):
        job = self.make_job()
        q1 = GenerationQueueService(self.store)
        queued = q1.enqueue(job["id"])
        other = CreativeOSStore(self.db)
        try:
            first = q1.claim_next("worker-a")
            second = GenerationQueueService(other).claim_next("worker-b")
            self.assertEqual(first["id"], queued["id"])
            self.assertIsNone(second)
            with self.assertRaises(ValueError):
                q1.start(first["id"], "wrong-token")
            running = q1.start(first["id"], first["claim_token"])
            self.assertEqual(running["state"], "RUNNING")
            self.assertEqual(running["attempt_count"], 1)
        finally:
            other.close()

    def test_ordering_restart_and_stale_recovery(self):
        slow = self.make_job("image")
        fast = self.make_job("video")
        q = GenerationQueueService(self.store)
        q.enqueue(slow["id"], priority=100)
        high = q.enqueue(fast["id"], priority=10)
        first = q.claim_next("worker", lease_seconds=1)
        self.assertEqual(first["id"], high["id"])
        queue_id = first["id"]
        token = first["claim_token"]
        q.start(queue_id, token)
        future = datetime.now(timezone.utc) + timedelta(seconds=5)
        self.store.close()
        self.store = CreativeOSStore(self.db)
        recovered = GenerationQueueService(self.store).recover_stale(future)
        row = next(r for r in recovered if r["id"] == queue_id)
        self.assertEqual(row["state"], "QUEUED")
        self.assertEqual(row["generation_job_id"], fast["id"])
        self.assertEqual(row["attempt_count"], 1)
        self.assertEqual(row["last_error_code"], "LEASE_EXPIRED")

    def test_retry_reuses_same_job_and_respects_limit(self):
        job = self.make_job()
        router = ProviderRouter()
        router.register(ProviderRegistration("FAIL", frozenset({"image"}), AlwaysFailProvider(), True))
        self.store.update("generation_jobs", job["id"], {"provider": "FAIL", "provider_snapshot": "FAIL"})
        queued = GenerationQueueService(self.store).enqueue(job["id"], max_attempts=2)
        worker = GenerationWorker(self.store, router, "worker-fail")
        first = worker.run_once()
        self.assertEqual(first["state"], "QUEUED")
        self.assertEqual(first["attempt_count"], 1)
        second = worker.run_once()
        self.assertEqual(second["state"], "FAILED")
        self.assertEqual(second["attempt_count"], 2)
        self.assertEqual(second["generation_job_id"], job["id"])
        self.assertEqual(self.store.get("generation_queue", queued["id"])["id"], queued["id"])
        self.assertEqual(len(self.store.list("generation_jobs")), 1)

    def test_cancellation_after_provider_return_rejects_output(self):
        job = self.make_job()
        router = ProviderRouter()
        router.register(ProviderRegistration("CANCEL", frozenset({"image"}), CancelDuringRunProvider(self.store), True))
        self.store.update("generation_jobs", job["id"], {"provider": "CANCEL", "provider_snapshot": "CANCEL"})
        queue = GenerationQueueService(self.store).enqueue(job["id"])
        result = GenerationWorker(self.store, router, "worker-cancel").run_once()
        self.assertEqual(result["state"], "CANCELLED")
        self.assertEqual(result["id"], queue["id"])
        self.assertEqual(self.store.list("generated_assets", {"generation_job_id": job["id"]}), [])

    def test_success_idempotency_and_no_duplicate_asset(self):
        job = self.make_job()
        q = GenerationQueueService(self.store)
        queued = q.enqueue(job["id"])
        worker = GenerationWorker(self.store, default_router(), "worker-ok")
        asset = worker.run_once()
        self.assertEqual(q.store.get("generation_queue", queued["id"])["state"], "SUCCEEDED")
        self.assertEqual(len(self.store.list("generated_assets", {"generation_job_id": job["id"]})), 1)
        q.store.conn.execute("UPDATE generation_queue SET state='QUEUED', finished_at=NULL WHERE id=?", (queued["id"],))
        q.store.conn.commit()
        same = worker.run_once()
        self.assertEqual(same["id"], asset["id"])
        self.assertEqual(len(self.store.list("generated_assets", {"generation_job_id": job["id"]})), 1)


if __name__ == "__main__":
    unittest.main()
