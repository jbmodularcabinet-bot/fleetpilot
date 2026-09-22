import tempfile
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.generation import DeterministicMockGenerationProvider, GenerationService

class FailingProvider:
    name = "FAIL"
    def generate(self, job):
        raise RuntimeError("forced provider failure")

class GenerationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "db.sqlite3"
        self.store = CreativeOSStore(self.db)
        self.assertEqual(self.store.migrate_to_latest(), 7)
        brand = BrandBrainService(self.store).load_fleetpilot_fixture()
        campaign = self.store.create("campaigns", {"brand_profile_id": brand["id"], "title": "Gen"})
        board = self.store.create("storyboards", {"campaign_id": campaign["id"], "title": "Board"})
        self.scene = self.store.create("scenes", {
            "storyboard_id": board["id"], "position": 1, "title": "Shot",
            "duration_seconds": 5, "scene_type": "AI_IMAGE", "generation_method": "GENERATIVE",
        })
        self.service = GenerationService(self.store, DeterministicMockGenerationProvider())

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _requirement(self):
        return self.service.create_requirement(self.scene["id"], {
            "asset_type": "image", "purpose": "hero", "description": "clean product hero",
            "width": 1920, "height": 1080, "aspect_ratio": "16:9", "priority": "HIGH",
        })

    def test_mock_generation_provenance_idempotency_and_review(self):
        req = self._requirement()
        job = self.service.create_job(req["id"], "MOCK", "mock-v1", "render hero", aspect_ratio="16:9")
        asset = self.service.run_job(job["id"])
        self.assertEqual(self.store.get("generation_jobs", job["id"])["state"], "SUCCEEDED")
        self.assertEqual(asset["prompt_snapshot"], "render hero")
        self.assertEqual(asset["provider_snapshot"], "MOCK")
        self.assertEqual(len(asset["checksum_sha256"]), 64)
        again = self.service.run_job(job["id"])
        self.assertEqual(again["id"], asset["id"])
        self.assertEqual(len(self.store.list("generated_assets", {"generation_job_id": job["id"]})), 1)
        reviewed = self.service.review_asset(asset["id"], "approved")
        self.assertEqual(reviewed["review_state"], "APPROVED")
        with self.assertRaises(ValueError):
            self.service.review_asset(asset["id"], "rejected")

    def test_failure_retry_preserves_diagnostics(self):
        req = self._requirement()
        failing = GenerationService(self.store, FailingProvider())
        job = failing.create_job(req["id"], "FAIL", "fail-v1", "fail me")
        with self.assertRaises(RuntimeError):
            failing.run_job(job["id"])
        failed = self.store.get("generation_jobs", job["id"])
        self.assertEqual(failed["state"], "FAILED")
        self.assertIn("forced provider failure", failed["error"])
        retry = failing.retry_failed(job["id"])
        self.assertEqual(retry["retry_of_id"], job["id"])
        self.assertEqual(retry["retry_count"], 1)
        self.assertEqual(retry["state"], "QUEUED")

    def test_v4_v5_rollback_reapply_preserves_storyboard(self):
        scene_id = self.scene["id"]
        self.assertEqual(self.store.rollback_to(4), 4)
        self.assertEqual(self.store.get("scenes", scene_id)["title"], "Shot")
        self.assertEqual(self.store.migrate_to_latest(), 7)
        self.assertEqual(self.store.get("scenes", scene_id)["title"], "Shot")

if __name__ == "__main__":
    unittest.main()
