import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.composition import CompositionService, discover_media_tools
from creativeos_db.cost_optimizer import CostOptimizer
from creativeos_db.director import CampaignBrief, DeterministicMockCreativeDirectorProvider
from creativeos_db.director_service import CreativeDirectorService
from creativeos_db.generation import GenerationService
from creativeos_db.qa import QAService, REQUIRED_CHECKS
from creativeos_db.queue import GenerationQueueService, GenerationWorker
from creativeos_db.router import default_router
from creativeos_db.voice import VoiceService
from tests.repro_fixtures import COMMITTED_HERO_SHA256, copy_committed_hero


REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"

HISTORICAL_PROOF_HASHES = {
    BACKEND / "generated" / "batch9-proof" / "proof.sqlite3":
        "62899dbd0f6d352bcfcaa86b5b021b2ef72528ba9f3746a1cdefa07ed4de1025",
    BACKEND / "generated" / "batch9-proof" / "proof_summary.json":
        "d06c84ff7f30553475176597696a09a65477d69b36d5fdddc38b8827d961d04d",
    BACKEND / "generated" / "batch10-proof" / "proof.sqlite3":
        "a146925b1008950fd74e4a68b5a3313cef4a95f1be05371369cc406ca0c5f9a5",
    BACKEND / "generated" / "batch10-proof" / "proof_summary.json":
        "e32f3dacdac5e690b87ed30499c762892c7cddbfcB537d3489ab6f4b84f3ca2a".lower(),
}

FIXTURE = {
    "id": "FLEETPILOT_GOLDEN_PATH_V1",
    "version": 1,
    "mode": "LOCAL_DETERMINISTIC_MOCK",
    "campaign": {
        "title": "FleetPilot Golden Path V1",
        "objective": "Demonstrate operational visibility for Philippine trucking owners.",
        "audience": "Philippine trucking and logistics owners operating 5-100+ trucks",
        "offer": "See trips, costs, delivery evidence and profitability in one operating system.",
        "cta": "Book a FleetPilot demo",
        "format": "Product Walkthrough",
        "duration_seconds": 4,
        "aspect_ratio": "16:9",
        "tone": "clear, operational, credible",
        "budget_minor": 50000,
    },
    "voice_text": "Know every trip. Know every cost. FleetPilot.",
    "review_note": "Batch 11 FleetPilot golden-path integration proof accepted.",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def historical_proof_status(test: unittest.TestCase) -> dict[str, object]:
    present = {path: path.is_file() for path in HISTORICAL_PROOF_HASHES}
    if not any(present.values()):
        return {"status": "UNAVAILABLE", "hashes": {}}
    test.assertTrue(
        all(present.values()),
        "historical Batch 9/10 proof evidence must be complete when present",
    )
    observed = {
        str(path): sha256(path)
        for path in HISTORICAL_PROOF_HASHES
    }
    expected = {
        str(path): digest
        for path, digest in HISTORICAL_PROOF_HASHES.items()
    }
    test.assertEqual(observed, expected)
    return {"status": "VERIFIED", "hashes": observed}


def _probe_image(ffprobe: Path, path: Path) -> tuple[int, int] | None:
    result = subprocess.run(
        [str(ffprobe), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=20, shell=False,
    )
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not streams:
        return None
    return int(streams[0].get("width") or 0), int(streams[0].get("height") or 0)


def resolve_composition_visual(
    ffprobe: Path, proof_root: Path
) -> dict[str, str | int | None]:
    path = copy_committed_hero(REPO, proof_root)
    dims = _probe_image(ffprobe, path)
    if not dims:
        raise RuntimeError("committed hero.png is not readable by ffprobe")
    return {
        "source_type": "COMMITTED_TEST_ASSET",
        "fixture_id": "HERO_PNG_SHA256_V1",
        "path": str(path),
        "sha256": COMMITTED_HERO_SHA256,
        "width": dims[0],
        "height": dims[1],
        "creation_method": "copy of tracked app/src/assets/hero.png",
        "logo_path": None,
        "logo_sha256": None,
    }


def golden_brief(brand_id: str) -> CampaignBrief:
    return CampaignBrief(
        brand_profile_id=brand_id,
        objective=FIXTURE["campaign"]["objective"],
        target_audience=FIXTURE["campaign"]["audience"],
        awareness_level="problem-aware",
        pain_points=["fragmented operations"],
        core_offer=FIXTURE["campaign"]["offer"],
        cta=FIXTURE["campaign"]["cta"],
        campaign_format=FIXTURE["campaign"]["format"],
        duration_seconds=FIXTURE["campaign"]["duration_seconds"],
        aspect_ratio="16:9",
        language="English",
        tone=FIXTURE["campaign"]["tone"],
        presenter_mode="none",
        real_ui_percent=0,
        generated_percent=100,
        budget_preference="Controlled proof",
        quality_preference="High",
        production_constraints=["local deterministic proof only"],
    )


class Batch11GoldenPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proof_root = Path(self.tmp.name).resolve()
        self.proof_db = self.proof_root / "proof.sqlite3"
        self.proof_summary = self.proof_root / "proof_summary.json"
        self.historical_proof = historical_proof_status(self)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fleetpilot_golden_path(self):
        ffmpeg, ffprobe = discover_media_tools()
        visual = resolve_composition_visual(ffprobe, self.proof_root)
        visual_path = Path(str(visual["path"]))
        visual_before = sha256(visual_path)
        self.assertEqual(visual_before, COMMITTED_HERO_SHA256)

        store = CreativeOSStore(self.proof_db)
        self.assertEqual(store.migrate_to_latest(), 10)
        try:
            brand = BrandBrainService(store).load_fleetpilot_fixture()
            self.assertEqual(brand["name"], "FleetPilot")

            campaign = store.create("campaigns", {
                "brand_profile_id": brand["id"],
                "title": FIXTURE["campaign"]["title"],
                "objective": FIXTURE["campaign"]["objective"],
                "audience": FIXTURE["campaign"]["audience"],
                "offer": FIXTURE["campaign"]["offer"],
                "cta": FIXTURE["campaign"]["cta"],
                "format": FIXTURE["campaign"]["format"],
                "duration_seconds": FIXTURE["campaign"]["duration_seconds"],
                "aspect_ratio": "16:9",
                "tone": FIXTURE["campaign"]["tone"],
            })

            director = CreativeDirectorService(store, DeterministicMockCreativeDirectorProvider())
            draft = director.generate_plan(campaign["id"], golden_brief(brand["id"]), brand)
            approved = director.approve_plan(draft["id"])
            self.assertEqual(approved["status"], "APPROVED")
            materialized = director.materialize_storyboard(draft["id"], "FleetPilot Golden Path V1")
            board = materialized["storyboard"]
            scenes = materialized["scenes"]
            self.assertGreaterEqual(len(scenes), 1)
            scene = next(s for s in scenes if s["generation_method"] == "GENERATIVE")

            router = default_router()
            optimizer = CostOptimizer(store, router)
            optimizer.set_campaign_budget(campaign["id"], FIXTURE["campaign"]["budget_minor"], "PHP", 2)
            profile = optimizer.create_profile({
                "provider": "MOCK",
                "model": "mock-v1",
                "capability": "image",
                "quality_tier": "HIGH",
                "currency": "PHP",
                "currency_minor_exponent": 2,
                "fixed_cost_minor": 100,
                "version": 1,
                "effective_at": "2026-09-22T00:00:00+00:00",
                "source_label": "BATCH11_GOLDEN_PATH",
            })

            generation = GenerationService(store, router.resolve("image", "MOCK"))
            requirement = generation.create_requirement(scene["id"], {
                "asset_type": "image",
                "purpose": "FleetPilot golden-path owner operations visual",
                "description": "Deterministic local proof visual for FleetPilot integration verification",
                "width": 640,
                "height": 360,
                "aspect_ratio": "16:9",
                "priority": "NORMAL",
                "status": "PENDING",
            })

            cost_result = optimizer.recommend(requirement["id"], "HIGH")
            recommendation = cost_result["recommendation"]
            estimates = cost_result["estimates"]
            self.assertTrue(estimates)
            selected = next(e for e in estimates if e["is_recommended"])
            self.assertEqual(selected["budget_state"], "WITHIN_BUDGET")
            cost_created_at = recommendation["created_at"]

            gen_job = generation.create_job(
                requirement["id"], "MOCK", "mock-v1",
                "FleetPilot owner operations visibility visual",
                aspect_ratio="16:9",
            )
            queue = GenerationQueueService(store).enqueue(gen_job["id"])
            self.assertLessEqual(cost_created_at, gen_job["created_at"])
            worker = GenerationWorker(store, router, "batch11-golden-worker")
            worker_result = worker.run_once()
            self.assertIsNotNone(worker_result)

            gen_job = store.get("generation_jobs", gen_job["id"])
            queue = store.get("generation_queue", queue["id"])
            assets = store.list("generated_assets", {"generation_job_id": gen_job["id"]})
            self.assertEqual(gen_job["state"], "SUCCEEDED")
            self.assertEqual(queue["state"], "SUCCEEDED")
            self.assertEqual(len(assets), 1)
            generated_asset = assets[0]
            self.assertTrue(generated_asset["checksum_sha256"])
            self.assertTrue(str(generated_asset["output_path"]).startswith("mock://"))
            self.assertNotEqual(str(generated_asset["output_path"]), str(visual_path))

            voice_service = VoiceService(store, self.proof_root / "voice")
            voice_job = voice_service.create_job(
                scene["id"], FIXTURE["voice_text"], "en", "mock-ainsley", gen_job["id"]
            )
            voice = voice_service.run_job(voice_job["id"])
            self.assertEqual(voice["status"], "SUCCEEDED")

            composition = CompositionService(
                store, self.proof_root, self.proof_root, ffmpeg, ffprobe
            )
            timeline_created = composition.create_timeline(
                campaign["id"], board["id"], [{
                    "scene_id": scene["id"],
                    "generated_asset_id": generated_asset["id"],
                    "duration_ms": 4000,
                    "visual_path": str(visual_path),
                    "audio_path": voice["output_path"],
                    "transition": {"type": "cut"},
                }],
                target_width=640, target_height=360, aspect_ratio="16:9", fps=24,
            )
            timeline = timeline_created["timeline"]
            entries = timeline_created["entries"]
            render = composition.render_preview(timeline["id"])
            self.assertEqual(render["status"], "SUCCEEDED")
            self.assertEqual(render["exit_code"], 0)
            self.assertTrue(Path(render["output_path"]).is_file())

            visual_after_render = sha256(visual_path)
            self.assertEqual(visual_before, visual_after_render)

            qa_service = QAService(store, ffprobe_path=ffprobe)
            qa_run = qa_service.create_qa_run(render["id"])
            self.assertEqual(qa_run["attempt_version"], 1)
            qa_run = qa_service.execute_qa_run(qa_run["id"])
            qa_checks = qa_service.list_qa_checks(qa_run["id"])

            self.assertEqual(qa_run["manifest_id"], "CREATIVEOS_RENDER_QA")
            self.assertEqual(str(qa_run["manifest_version"]), "1")
            self.assertEqual(str(qa_run["rule_version"]), "1")
            self.assertEqual(qa_run["lifecycle_state"], "FINALIZED")
            self.assertEqual(qa_run["overall_result"], "PASS")
            self.assertEqual(qa_run["required_check_count"], 11)
            self.assertEqual(qa_run["actual_check_count"], 11)
            self.assertEqual({c["check_id"] for c in qa_checks}, set(REQUIRED_CHECKS))
            self.assertEqual(len(qa_checks), 11)
            self.assertTrue(all(c["result"] == "PASS" for c in qa_checks))
            self.assertTrue(all(c["severity"] == "CRITICAL" for c in qa_checks))
            self.assertTrue(all(str(c["check_version"]) == "1" for c in qa_checks))

            again = qa_service.create_qa_run(render["id"])
            self.assertEqual(again["id"], qa_run["id"])
            self.assertEqual(again["base_identity_key"], qa_run["base_identity_key"])
            self.assertEqual(again["attempt_identity_key"], qa_run["attempt_identity_key"])
            self.assertEqual(again["attempt_version"], 1)
            self.assertEqual(len(store.list("qa_runs", {"render_job_id": render["id"]})), 1)
            self.assertEqual(len(store.list("render_attempts", {"render_job_id": render["id"]})), 1)

            automated_before_review = dict(qa_service.get_qa_run(qa_run["id"]))
            checks_before_review = qa_service.list_qa_checks(qa_run["id"])
            review = qa_service.record_qa_review(
                qa_run["id"], "ACCEPTED", FIXTURE["review_note"]
            )
            self.assertEqual(review["review_state"], "ACCEPTED")
            self.assertEqual(qa_service.get_qa_run(qa_run["id"]), automated_before_review)
            self.assertEqual(qa_service.list_qa_checks(qa_run["id"]), checks_before_review)

            summary = {
                "fixture_id": FIXTURE["id"],
                "fixture_version": FIXTURE["version"],
                "fixture_mode": FIXTURE["mode"],
                "schema_version": store.schema_version(),
                "brand_id": brand["id"],
                "campaign_id": campaign["id"],
                "director_plan_id": draft["id"],
                "director_scene_count": len(scenes),
                "storyboard_id": board["id"],
                "scene_ids": [s["id"] for s in scenes],
                "selected_scene_id": scene["id"],
                "asset_requirement_ids": [requirement["id"]],
                "provider_cost_profile_id": profile["id"],
                "cost_recommendation_id": recommendation["id"],
                "cost_estimate_ids": [e["id"] for e in estimates],
                "selected_cost_estimate_id": selected["id"],
                "budget_state": selected["budget_state"],
                "generation_job_ids": [gen_job["id"]],
                "queue_ids": [queue["id"]],
                "generated_asset_ids": [generated_asset["id"]],
                "generated_asset_checksums": [generated_asset["checksum_sha256"]],
                "generated_asset_output_path": generated_asset["output_path"],
                "generated_asset_is_composition_visual": False,
                "composition_visual_source": visual["source_type"],
                "composition_visual_fixture_id": visual["fixture_id"],
                "composition_visual_path": str(visual_path),
                "composition_visual_creation_method": visual["creation_method"],
                "composition_visual_checksum_before": visual_before,
                "composition_visual_checksum_after": visual_after_render,
                "voice_job_ids": [voice["id"]],
                "voice_output_paths": [voice["output_path"]],
                "voice_checksums": [voice["checksum_sha256"]],
                "timeline_id": timeline["id"],
                "timeline_entry_ids": [e["id"] for e in entries],
                "render_job_id": render["id"],
                "render_identity": render["render_identity"],
                "render_output_path": render["output_path"],
                "render_checksum": render["output_checksum_sha256"],
                "ffmpeg_version": render["ffmpeg_version"],
                "qa_run_id": qa_run["id"],
                "qa_base_identity": qa_run["base_identity_key"],
                "qa_attempt_identity": qa_run["attempt_identity_key"],
                "qa_attempt_version": qa_run["attempt_version"],
                "qa_result": qa_run["overall_result"],
                "qa_check_results": [
                    {
                        "check_id": c["check_id"],
                        "result": c["result"],
                        "severity": c["severity"],
                        "check_version": c["check_version"],
                    } for c in qa_checks
                ],
                "review_state": review["review_state"],
                "review_note": review["reviewer_note"],
                "historical_proof": self.historical_proof,
            }
            self.proof_summary.write_text(
                json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
            )
            proof_ids = {
                "brand": brand["id"],
                "campaign": campaign["id"],
                "plan": draft["id"],
                "board": board["id"],
                "scene": scene["id"],
                "requirement": requirement["id"],
                "job": gen_job["id"],
                "queue": queue["id"],
                "asset": generated_asset["id"],
                "voice": voice["id"],
                "timeline": timeline["id"],
                "render": render["id"],
                "qa": qa_run["id"],
            }
        finally:
            store.close()

        reopened = CreativeOSStore(self.proof_db)
        try:
            self.assertEqual(reopened.schema_version(), 10)
            self.assertEqual(reopened.get("brand_profiles", proof_ids["brand"])["id"], proof_ids["brand"])
            self.assertEqual(reopened.get("campaigns", proof_ids["campaign"])["id"], proof_ids["campaign"])
            self.assertEqual(reopened.get("director_plans", proof_ids["plan"])["status"], "APPROVED")
            self.assertEqual(reopened.get("storyboards", proof_ids["board"])["id"], proof_ids["board"])
            self.assertEqual(reopened.get("generation_jobs", proof_ids["job"])["state"], "SUCCEEDED")
            self.assertEqual(reopened.get("generation_queue", proof_ids["queue"])["state"], "SUCCEEDED")
            self.assertEqual(reopened.get("voice_jobs", proof_ids["voice"])["status"], "SUCCEEDED")
            self.assertEqual(reopened.get("render_jobs", proof_ids["render"])["status"], "SUCCEEDED")
            self.assertEqual(reopened.get("qa_runs", proof_ids["qa"])["overall_result"], "PASS")
        finally:
            reopened.close()

        self.assertEqual(sha256(visual_path), visual_before)
        self.assertEqual(historical_proof_status(self), self.historical_proof)
        self.assertTrue(self.proof_summary.is_file())


if __name__ == "__main__":
    unittest.main()
