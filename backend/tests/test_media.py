import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.composition import CompositionService, DURATION_TOLERANCE_SECONDS, discover_media_tools
from creativeos_db.cost_optimizer import CostOptimizer
from creativeos_db.generation import GenerationService, DeterministicMockGenerationProvider
from creativeos_db.queue import GenerationQueueService
from creativeos_db.router import ProviderRegistration, ProviderRouter
from creativeos_db.voice import DeterministicMockVoiceAdapter, VoiceService


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FailingVoiceAdapter(DeterministicMockVoiceAdapter):
    def synthesize(self, text, language, voice_id, output_path):
        raise RuntimeError("forced voice failure")


class Batch9MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "assets").mkdir()
        source_hero = Path(__file__).resolve().parents[2] / "app" / "src" / "assets" / "hero.png"
        self.visual = self.root / "assets" / "hero.png"
        shutil.copy2(source_hero, self.visual)
        self.db = self.root / "creativeos.sqlite3"
        self.store = CreativeOSStore(self.db)
        self.assertEqual(self.store.migrate_to_latest(), 10)
        brand = BrandBrainService(self.store).load_fleetpilot_fixture()
        self.campaign = self.store.create("campaigns", {"brand_profile_id": brand["id"], "title": "Media"})
        self.board = self.store.create("storyboards", {"campaign_id": self.campaign["id"], "title": "Media"})
        self.scene = self.store.create("scenes", {
            "storyboard_id": self.board["id"], "position": 1, "title": "Preview",
            "duration_seconds": 2, "scene_type": "AI_IMAGE", "generation_method": "GENERATIVE",
        })
        self.ffmpeg, self.ffprobe = discover_media_tools()
        self.output_root = self.root / "generated"

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def voice_service(self, adapter=None):
        return VoiceService(self.store, self.output_root / "voice", adapter=adapter)

    def composition(self):
        return CompositionService(
            self.store, self.root, self.output_root, self.ffmpeg, self.ffprobe
        )

    def make_voice(self, text="Control your fleet with confidence"):
        service = self.voice_service()
        job = service.create_job(self.scene["id"], text, "en", "mock-ainsley")
        return service.run_job(job["id"])

    def make_timeline(self, duration_ms=1200, audio=True, width=320, height=180):
        voice = self.make_voice() if audio else None
        return self.composition().create_timeline(
            self.campaign["id"], self.board["id"], [{
                "scene_id": self.scene["id"], "duration_ms": duration_ms,
                "visual_path": str(self.visual),
                "audio_path": voice["output_path"] if voice else None,
                "transition": {"type": "cut"},
            }], target_width=width, target_height=height, aspect_ratio="16:9", fps=24,
        )

    def test_mock_voice_determinism_checksum_and_restart(self):
        a = self.make_voice("same deterministic line")
        b = self.make_voice("same deterministic line")
        self.assertEqual(a["checksum_sha256"], b["checksum_sha256"])
        self.assertEqual(a["duration_ms"], b["duration_ms"])
        self.assertEqual(a["status"], "SUCCEEDED")
        job_id = a["id"]
        self.store.close()
        self.store = CreativeOSStore(self.db)
        reloaded = self.store.get("voice_jobs", job_id)
        self.assertEqual(reloaded["checksum_sha256"], a["checksum_sha256"])
        self.assertTrue(Path(reloaded["output_path"]).exists())

    def test_failed_voice_preserves_diagnostics(self):
        service = self.voice_service(FailingVoiceAdapter())
        job = service.create_job(self.scene["id"], "fail this voice")
        with self.assertRaises(RuntimeError):
            service.run_job(job["id"])
        failed = self.store.get("voice_jobs", job["id"])
        self.assertEqual(failed["status"], "FAILED")
        self.assertIn("forced voice failure", failed["error"])

    def test_timeline_ordering_and_restart_persistence(self):
        voice = self.make_voice()
        service = self.composition()
        created = service.create_timeline(
            self.campaign["id"], self.board["id"], [
                {"scene_id": self.scene["id"], "duration_ms": 500, "visual_path": str(self.visual), "audio_path": voice["output_path"]},
                {"scene_id": self.scene["id"], "duration_ms": 700, "visual_path": str(self.visual), "audio_path": voice["output_path"]},
            ], target_width=320, target_height=180, fps=24,
        )
        tid = created["timeline"]["id"]
        self.assertEqual([e["start_ms"] for e in created["entries"]], [0, 500])
        self.store.close()
        self.store = CreativeOSStore(self.db)
        loaded = self.composition().load_timeline(tid)
        self.assertEqual([e["sequence"] for e in loaded["entries"]], [1, 2])
        self.assertEqual([e["start_ms"] for e in loaded["entries"]], [0, 500])

    def test_command_builder_safety_and_path_validation(self):
        timeline = self.make_timeline(audio=False)["timeline"]
        service = self.composition()
        good_output = self.output_root / "previews" / "safe.mp4"
        args = service.build_ffmpeg_args(timeline["id"], good_output)
        self.assertIsInstance(args, list)
        self.assertIn(str(self.visual), args)
        self.assertNotIn("shell", args)
        with self.assertRaises(ValueError):
            service.build_ffmpeg_args(timeline["id"], self.root.parent / "escape.mp4")
        with self.assertRaises(ValueError):
            service.create_timeline(
                self.campaign["id"], self.board["id"], [{
                    "scene_id": self.scene["id"], "duration_ms": 1000,
                    "visual_path": str(self.root / "assets" / "missing;calc.exe.png"),
                }], target_width=320, target_height=180,
            )
        with self.assertRaises(ValueError):
            service.create_timeline(
                self.campaign["id"], self.board["id"], [{
                    "scene_id": self.scene["id"], "duration_ms": 0, "visual_path": str(self.visual),
                }], target_width=320, target_height=180,
            )
        with self.assertRaises(ValueError):
            service.create_timeline(
                self.campaign["id"], self.board["id"], [{
                    "scene_id": self.scene["id"], "duration_ms": 1000, "visual_path": str(self.visual),
                }], target_width=0, target_height=180,
            )

    def test_real_preview_ffprobe_idempotency_and_source_protection(self):
        timeline = self.make_timeline(duration_ms=1200, audio=True)["timeline"]
        before = sha(self.visual)
        service = self.composition()
        rendered = service.render_preview(timeline["id"])
        after = sha(self.visual)
        self.assertEqual(before, after)
        self.assertEqual(rendered["status"], "SUCCEEDED")
        self.assertEqual(rendered["exit_code"], 0)
        self.assertTrue(Path(rendered["output_path"]).is_file())
        probe = json.loads(rendered["probe_json"])
        streams = probe["ffprobe"]["streams"]
        video = next(s for s in streams if s["codec_type"] == "video")
        self.assertEqual((video["width"], video["height"]), (320, 180))
        self.assertTrue(any(s["codec_type"] == "audio" for s in streams))
        self.assertLessEqual(
            abs(probe["actual_duration_seconds"] - probe["expected_duration_seconds"]),
            DURATION_TOLERANCE_SECONDS,
        )
        again = service.render_preview(timeline["id"])
        self.assertEqual(again["id"], rendered["id"])
        attempts = self.store.list("render_attempts", {"render_job_id": rendered["id"]})
        self.assertEqual(len(attempts), 1)

    def test_failed_render_attempt_evidence_is_retained(self):
        bad_audio = self.root / "assets" / "broken.wav"
        bad_audio.write_text("not audio", encoding="utf-8")
        timeline = self.composition().create_timeline(
            self.campaign["id"], self.board["id"], [{
                "scene_id": self.scene["id"], "duration_ms": 800,
                "visual_path": str(self.visual), "audio_path": str(bad_audio),
            }], target_width=320, target_height=180, fps=24,
        )["timeline"]
        with self.assertRaises(RuntimeError):
            self.composition().render_preview(timeline["id"])
        jobs = self.store.list("render_jobs", {"timeline_id": timeline["id"]})
        self.assertEqual(jobs[0]["status"], "FAILED")
        attempts = self.store.list("render_attempts", {"render_job_id": jobs[0]["id"]})
        self.assertEqual(len(attempts), 1)
        self.assertIsNotNone(attempts[0]["exit_code"])
        self.assertTrue(attempts[0]["stderr_summary"] or attempts[0]["error"])

    def test_v7_v8_rollback_reapply_preserves_batch7_and_8_records(self):
        gen = GenerationService(self.store, DeterministicMockGenerationProvider())
        req = gen.create_requirement(self.scene["id"], {"asset_type": "image", "purpose": "proof"})
        job = gen.create_job(req["id"], "MOCK", "mock-v1", "proof")
        queue = GenerationQueueService(self.store).enqueue(job["id"])
        asset = gen.run_job(job["id"])
        router = ProviderRouter()
        router.register(ProviderRegistration("MOCK", frozenset({"image"}), DeterministicMockGenerationProvider(), True))
        opt = CostOptimizer(self.store, router)
        opt.set_campaign_budget(self.campaign["id"], 10000, "PHP", 2)
        profile = opt.create_profile({
            "provider": "MOCK", "model": "mock-v1", "capability": "image", "quality_tier": "HIGH",
            "currency": "PHP", "currency_minor_exponent": 2, "fixed_cost_minor": 100,
            "version": 1, "effective_at": "2026-09-22T00:00:00+00:00", "source_label": "TEST",
        })
        fx = opt.create_fx_snapshot({
            "from_currency": "USD", "to_currency": "PHP", "from_minor_exponent": 2,
            "to_minor_exponent": 2, "rate_decimal": "58.5", "rate_source": "TEST",
            "rate_effective_at": "2026-09-22T00:00:00+00:00", "captured_at": "2026-09-22T00:01:00+00:00",
        })
        result = opt.recommend(req["id"], "HIGH")
        estimate = result["estimates"][0]
        override = opt.record_override(result["recommendation"]["id"], estimate["id"], "proof override")
        ids = {
            "queue": queue["id"], "asset": asset["id"], "profile": profile["id"], "fx": fx["id"],
            "rec": result["recommendation"]["id"], "estimate": estimate["id"], "override": override["id"],
        }
        self.assertEqual(self.store.rollback_to(7), 7)
        self.assertEqual(self.store.get("generation_queue", ids["queue"])["id"], ids["queue"])
        self.assertEqual(self.store.get("generated_assets", ids["asset"])["id"], ids["asset"])
        self.assertEqual(self.store.get("provider_cost_profiles", ids["profile"])["id"], ids["profile"])
        self.assertEqual(self.store.get("fx_snapshots", ids["fx"])["id"], ids["fx"])
        self.assertEqual(self.store.get("cost_recommendations", ids["rec"])["id"], ids["rec"])
        self.assertEqual(self.store.get("cost_estimates", ids["estimate"])["id"], ids["estimate"])
        self.assertEqual(self.store.get("cost_overrides", ids["override"])["id"], ids["override"])
        self.assertEqual(self.store.migrate_to_latest(), 10)


if __name__ == "__main__":
    unittest.main()
