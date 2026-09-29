import copy
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.composition import discover_media_tools
from creativeos_db.cost_optimizer import CostOptimizer
from creativeos_db.generation import DeterministicMockGenerationProvider, GenerationService
from creativeos_db.migrations import MIGRATIONS
from creativeos_db.qa import QAEngineError, QAService, REQUIRED_CHECKS, derive_overall
from creativeos_db.queue import GenerationQueueService
from creativeos_db.router import default_router


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Batch10QATests(unittest.TestCase):
    PROTECTED = (
        "brand_profiles", "campaigns", "storyboards", "scenes",
        "generation_jobs", "generation_queue", "generated_assets",
        "provider_cost_profiles", "fx_snapshots", "cost_recommendations",
        "cost_estimates", "cost_overrides", "voice_jobs",
        "composition_timelines", "composition_timeline_entries",
        "render_jobs", "render_attempts",
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "qa.sqlite3"
        self.repo = Path(__file__).resolve().parents[2]
        self.proof_source = self.repo / "backend" / "generated" / "batch9-proof" / "proof.sqlite3"
        self.assertTrue(self.proof_source.is_file())

    def tearDown(self):
        self.tmp.cleanup()

    def _copy_proof_store(self):
        path = self.root / f"proof-{len(list(self.root.glob('proof-*.sqlite3')))}.sqlite3"
        shutil.copy2(self.proof_source, path)
        store = CreativeOSStore(path)
        self.assertEqual(store.migrate_to_latest(), 10)
        render = store.conn.execute(
            "SELECT * FROM render_jobs WHERE status='SUCCEEDED' ORDER BY created_at LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(render)
        return store, dict(render)

    def _run_clean(self):
        store, render = self._copy_proof_store()
        service = QAService(store)
        run = service.create_qa_run(render["id"])
        before_attempts = store.conn.execute("SELECT COUNT(*) FROM render_attempts").fetchone()[0]
        finalized = service.execute_qa_run(run["id"])
        after_attempts = store.conn.execute("SELECT COUNT(*) FROM render_attempts").fetchone()[0]
        self.assertEqual(before_attempts, after_attempts)
        return store, service, finalized

    def _checks_by_id(self, service, run_id):
        return {row["check_id"]: row for row in service.list_qa_checks(run_id)}

    def _new_v8_store(self):
        store = CreativeOSStore(self.db)
        for version in range(1, 9):
            store.conn.executescript(MIGRATIONS[version][0])
            store.conn.commit()
        self.assertEqual(store.schema_version(), 8)
        return store

    def _seed_batch0_9(self, store):
        brand = BrandBrainService(store).load_fleetpilot_fixture()
        campaign = store.create("campaigns", {
            "brand_profile_id": brand["id"], "title": "QA migration seed",
        })
        board = store.create("storyboards", {
            "campaign_id": campaign["id"], "title": "QA migration board",
        })
        scene = store.create("scenes", {
            "storyboard_id": board["id"], "position": 1, "title": "QA migration scene",
            "duration_seconds": 2, "scene_type": "AI_IMAGE", "generation_method": "GENERATIVE",
        })
        gen = GenerationService(store, DeterministicMockGenerationProvider())
        req = gen.create_requirement(scene["id"], {"asset_type": "image", "purpose": "migration proof"})
        job = gen.create_job(req["id"], "MOCK", "mock-v1", "migration proof")
        queue = GenerationQueueService(store).enqueue(job["id"])
        asset = gen.run_job(job["id"])

        opt = CostOptimizer(store, default_router())
        opt.set_campaign_budget(campaign["id"], 10000, "PHP", 2)
        profile = opt.create_profile({
            "provider": "MOCK", "model": "mock-v1", "capability": "image",
            "quality_tier": "HIGH", "currency": "PHP", "currency_minor_exponent": 2,
            "fixed_cost_minor": 100, "version": 1,
            "effective_at": "2026-09-22T00:00:00+00:00", "source_label": "MIGRATION_TEST",
        })
        fx = opt.create_fx_snapshot({
            "from_currency": "USD", "to_currency": "PHP", "from_minor_exponent": 2,
            "to_minor_exponent": 2, "rate_decimal": "58.5", "rate_source": "MIGRATION_TEST",
            "rate_effective_at": "2026-09-22T00:00:00+00:00",
            "captured_at": "2026-09-22T00:01:00+00:00",
        })
        rec = opt.recommend(req["id"], "HIGH")
        estimate = rec["estimates"][0]
        override = opt.record_override(rec["recommendation"]["id"], estimate["id"], "migration proof override")

        voice = store.create("voice_jobs", {
            "scene_id": scene["id"], "provider": "MOCK", "model": "deterministic-sine-v1",
            "voice_id": "mock-proof", "text_snapshot": "migration proof", "language": "en",
            "status": "SUCCEEDED", "output_path": "mock://voice/proof.wav",
            "duration_ms": 2000, "checksum_sha256": "v" * 64,
        })
        timeline = store.create("composition_timelines", {
            "campaign_id": campaign["id"], "storyboard_id": board["id"],
            "target_width": 640, "target_height": 360, "aspect_ratio": "16:9", "fps": 24,
        })
        entry = store.create("composition_timeline_entries", {
            "timeline_id": timeline["id"], "sequence": 1, "scene_id": scene["id"],
            "generated_asset_id": asset["id"], "start_ms": 0, "duration_ms": 2000,
            "visual_path": "mock://visual/proof.png", "audio_path": voice["output_path"],
            "transition_json": {"type": "cut"},
        })
        render = store.create("render_jobs", {
            "timeline_id": timeline["id"], "render_identity": "r" * 64,
            "status": "SUCCEEDED", "output_path": "mock://render/proof.mp4",
            "command_args_json": ["-i", "proof"], "ffmpeg_path": "ffmpeg",
            "ffmpeg_version": "9.0.2", "exit_code": 0,
            "stdout_summary": "", "stderr_summary": "",
            "output_checksum_sha256": "o" * 64,
            "probe_json": {
                "expected_duration_seconds": 2.0, "actual_duration_seconds": 2.0,
                "duration_tolerance_seconds": 0.2, "audio_required": True,
                "source_checksums_before": {"mock://visual/proof.png": "s" * 64},
                "source_checksums_after": {"mock://visual/proof.png": "s" * 64},
                "ffprobe": {"format": {"duration": "2.000000"}, "streams": [
                    {"codec_type": "video", "width": 640, "height": 360},
                    {"codec_type": "audio"},
                ]},
            },
        })
        attempt = store.create("render_attempts", {
            "render_job_id": render["id"], "started_at": "2026-09-22T00:02:00+00:00",
            "finished_at": "2026-09-22T00:02:02+00:00", "exit_code": 0,
            "stdout_summary": "", "stderr_summary": "", "error": None,
        })
        return {
            "brand_profiles": brand["id"], "campaigns": campaign["id"],
            "storyboards": board["id"], "scenes": scene["id"],
            "generation_jobs": job["id"], "generation_queue": queue["id"],
            "generated_assets": asset["id"], "provider_cost_profiles": profile["id"],
            "fx_snapshots": fx["id"], "cost_recommendations": rec["recommendation"]["id"],
            "cost_estimates": estimate["id"], "cost_overrides": override["id"],
            "voice_jobs": voice["id"], "composition_timelines": timeline["id"],
            "composition_timeline_entries": entry["id"], "render_jobs": render["id"],
            "render_attempts": attempt["id"],
        }

    def _snapshot(self, store, ids):
        rows, counts = {}, {}
        for table in self.PROTECTED:
            counts[table] = store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            row = store.conn.execute(f"SELECT * FROM {table} WHERE id=?", (ids[table],)).fetchone()
            self.assertIsNotNone(row, table)
            rows[table] = dict(row)
        return {"rows": rows, "counts": counts}
    def test_v8_v9_rollback_reapply_preserves_batch0_9_evidence(self):
        store = self._new_v8_store()
        try:
            ids = self._seed_batch0_9(store)
            baseline = self._snapshot(store, ids)
            self.assertEqual(store.foreign_key_violations(), [])

            store.conn.executescript(MIGRATIONS[9][0])
            store.conn.commit()
            self.assertEqual(store.schema_version(), 9)
            qa = store.create("qa_runs", {
                "render_job_id": ids["render_jobs"], "render_identity_snapshot": "r" * 64,
                "render_checksum_snapshot": "o" * 64, "manifest_id": "CREATIVEOS_QA",
                "manifest_version": "1", "rule_version": "1", "base_identity_key": "b" * 64,
                "attempt_version": 1, "attempt_identity_key": "a" * 64,
                "lifecycle_state": "FINALIZED", "overall_result": "PASS",
                "required_checks_json": ["OUTPUT_EXISTS"], "required_check_count": 1,
                "actual_check_count": 1, "started_at": "2026-09-22T00:03:00+00:00",
                "finished_at": "2026-09-22T00:03:01+00:00",
                "finalized_at": "2026-09-22T00:03:01+00:00",
            })
            store.create("qa_check_results", {
                "qa_run_id": qa["id"], "check_id": "OUTPUT_EXISTS", "check_version": "1",
                "result": "PASS", "severity": "CRITICAL", "expected_json": {"exists": True},
                "observed_json": {"exists": True}, "evidence_json": {"path": "mock"},
                "message": "present",
            })
            store.create("qa_reviews", {"qa_run_id": qa["id"], "review_state": "PENDING"})
            self.assertEqual(self._snapshot(store, ids), baseline)
            self.assertEqual(store.foreign_key_violations(), [])

            self.assertEqual(store.rollback_to(8), 8)
            for table in ("qa_runs", "qa_check_results", "qa_reviews"):
                self.assertIsNone(store.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone())
            self.assertEqual(self._snapshot(store, ids), baseline)
            self.assertEqual(store.foreign_key_violations(), [])
            self.assertEqual(store.get("render_jobs", ids["render_jobs"])["render_identity"], "r" * 64)

            self.assertEqual(store.migrate_to_latest(), 10)
            self.assertEqual(self._snapshot(store, ids), baseline)
            self.assertEqual(store.foreign_key_violations(), [])
            qa2 = store.create("qa_runs", {
                "render_job_id": ids["render_jobs"], "render_identity_snapshot": "r" * 64,
                "render_checksum_snapshot": "o" * 64, "manifest_id": "CREATIVEOS_QA",
                "manifest_version": "1", "rule_version": "1", "base_identity_key": "c" * 64,
                "attempt_version": 1, "attempt_identity_key": "d" * 64,
                "lifecycle_state": "PENDING", "required_checks_json": ["OUTPUT_EXISTS"],
                "required_check_count": 1, "actual_check_count": 0,
            })
            self.assertEqual(qa2["lifecycle_state"], "PENDING")
        finally:
            store.close()

    def test_create_qa_run_is_idempotent(self):
        store, render = self._copy_proof_store()
        try:
            service = QAService(store)
            first = service.create_qa_run(render["id"])
            second = service.create_qa_run(render["id"])
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(first["attempt_version"], 1)
            self.assertEqual(len(store.list("qa_runs")), 1)
        finally:
            store.close()

    def test_concurrent_create_has_single_authoritative_attempt(self):
        store, render = self._copy_proof_store()
        db_path = store.db_path
        render_id = render["id"]
        store.close()
        ids, errors = [], []
        lock = threading.Lock()

        def worker():
            local = CreativeOSStore(db_path)
            try:
                row = QAService(local).create_qa_run(render_id)
                with lock:
                    ids.append(row["id"])
            except Exception as exc:
                with lock:
                    errors.append(exc)
            finally:
                local.close()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(set(ids)), 1)
        check = CreativeOSStore(db_path)
        try:
            self.assertEqual(len(check.list("qa_runs")), 1)
        finally:
            check.close()

    def test_error_retry_is_idempotent_and_preserves_prior_attempt(self):
        store, render = self._copy_proof_store()
        try:
            def engine_fault(_path):
                raise OSError("forced ffprobe engine failure")

            failing = QAService(store, probe_runner=engine_fault)
            first = failing.create_qa_run(render["id"])
            first = failing.execute_qa_run(first["id"])
            self.assertEqual(first["lifecycle_state"], "ERROR")
            self.assertIsNone(first["overall_result"])
            snapshot = dict(first)

            second = failing.retry_error_qa_run(first["id"])
            same_second = failing.retry_error_qa_run(first["id"])
            self.assertEqual(second["id"], same_second["id"])
            self.assertEqual(second["attempt_version"], 2)
            self.assertEqual(second["base_identity_key"], first["base_identity_key"])
            self.assertNotEqual(second["attempt_identity_key"], first["attempt_identity_key"])
            self.assertEqual(failing.get_qa_run(first["id"]), snapshot)

            second_error = failing.execute_qa_run(second["id"])
            self.assertEqual(second_error["lifecycle_state"], "ERROR")
            third = failing.retry_error_qa_run(second_error["id"])
            same_third = failing.retry_error_qa_run(second_error["id"])
            self.assertEqual(third["id"], same_third["id"])
            self.assertEqual(third["attempt_version"], 3)
        finally:
            store.close()

    def test_changed_render_or_rule_creates_new_base_identity(self):
        store, render = self._copy_proof_store()
        try:
            service = QAService(store)
            first = service.create_qa_run(render["id"])
            store.conn.execute(
                "UPDATE render_jobs SET output_checksum_sha256=? WHERE id=?",
                ("0" * 64, render["id"]),
            )
            store.conn.commit()
            changed = service.create_qa_run(render["id"])
            self.assertNotEqual(first["base_identity_key"], changed["base_identity_key"])

            newer = QAService(store)
            newer.rule_version = "2"
            rule_changed = newer.create_qa_run(render["id"])
            self.assertNotEqual(changed["base_identity_key"], rule_changed["base_identity_key"])
        finally:
            store.close()
    def test_lifecycle_valid_transitions(self):
        store, service, finalized = self._run_clean()
        try:
            self.assertEqual(finalized["lifecycle_state"], "FINALIZED")
            self.assertEqual(finalized["overall_result"], "PASS")
            self.assertIsNotNone(finalized["started_at"])
            self.assertIsNotNone(finalized["finished_at"])
            self.assertIsNotNone(finalized["finalized_at"])
        finally:
            store.close()

    def test_lifecycle_rejects_terminal_mutation(self):
        store, service, finalized = self._run_clean()
        try:
            with self.assertRaises(ValueError):
                service.execute_qa_run(finalized["id"])
            with self.assertRaises(ValueError):
                store.update("qa_runs", finalized["id"], {"lifecycle_state": "RUNNING"})
            checks = service.list_qa_checks(finalized["id"])
            with self.assertRaises(ValueError):
                store.update("qa_check_results", checks[0]["id"], {"result": "FAIL"})
        finally:
            store.close()

    def test_engine_failure_ends_error_without_overall_result(self):
        store, render = self._copy_proof_store()
        try:
            def fault(_path):
                raise OSError("forced engine failure")
            service = QAService(store, probe_runner=fault)
            run = service.create_qa_run(render["id"])
            result = service.execute_qa_run(run["id"])
            self.assertEqual(result["lifecycle_state"], "ERROR")
            self.assertIsNone(result["overall_result"])
            self.assertEqual(result["error_code"], "QA_ENGINE_ERROR")
        finally:
            store.close()

    def test_required_manifest_integrity(self):
        checks = [
            {"check_id": check_id, "result": "PASS"}
            for check_id in REQUIRED_CHECKS
        ]
        self.assertEqual(derive_overall(checks), "PASS")
        self.assertEqual(derive_overall(checks[:-1]), "FAIL")
        duplicate = copy.deepcopy(checks[:-1]) + [copy.deepcopy(checks[0])]
        self.assertEqual(derive_overall(duplicate), "FAIL")

    def test_fail_warn_pass_precedence(self):
        checks = [{"check_id": cid, "result": "PASS"} for cid in REQUIRED_CHECKS]
        self.assertEqual(derive_overall(checks), "PASS")
        checks[0]["result"] = "WARN"
        self.assertEqual(derive_overall(checks), "WARN")
        checks[1]["result"] = "FAIL"
        self.assertEqual(derive_overall(checks), "FAIL")

    def test_incomplete_manifest_cannot_pass(self):
        checks = [{"check_id": cid, "result": "PASS"} for cid in REQUIRED_CHECKS[:-2]]
        self.assertEqual(derive_overall(checks), "FAIL")

    def test_atomic_finalization_rejects_partial_evidence(self):
        store, render = self._copy_proof_store()
        try:
            service = QAService(store)
            run = service.create_qa_run(render["id"])
            store.conn.execute(
                "UPDATE qa_runs SET lifecycle_state='RUNNING', started_at='x' WHERE id=?",
                (run["id"],),
            )
            store.conn.commit()
            with self.assertRaises(ValueError):
                service._finalize(run["id"], [{
                    "check_id": REQUIRED_CHECKS[0], "check_version": "1", "result": "PASS",
                    "severity": "CRITICAL", "expected_json": {}, "observed_json": {},
                    "evidence_json": {}, "message": "partial",
                }])
            current = service.get_qa_run(run["id"])
            self.assertEqual(current["lifecycle_state"], "RUNNING")
            self.assertIsNone(current["overall_result"])
            self.assertEqual(service.list_qa_checks(run["id"]), [])
        finally:
            store.close()

    def test_verified_batch9_render_finalizes_pass(self):
        store, service, finalized = self._run_clean()
        try:
            self.assertEqual(finalized["lifecycle_state"], "FINALIZED")
            self.assertEqual(finalized["overall_result"], "PASS")
            checks = service.list_qa_checks(finalized["id"])
            self.assertEqual([row["check_id"] for row in checks], list(REQUIRED_CHECKS))
            self.assertTrue(all(row["result"] == "PASS" for row in checks))
            again = service.create_qa_run(finalized["render_job_id"])
            self.assertEqual(again["id"], finalized["id"])
        finally:
            store.close()

    def test_missing_output_finalizes_fail(self):
        store, render = self._copy_proof_store()
        try:
            missing = self.root / "not-there.mp4"
            store.conn.execute("UPDATE render_jobs SET output_path=? WHERE id=?", (str(missing), render["id"]))
            store.conn.commit()
            service = QAService(store)
            result = service.execute_qa_run(service.create_qa_run(render["id"])["id"])
            self.assertEqual((result["lifecycle_state"], result["overall_result"]), ("FINALIZED", "FAIL"))
            self.assertEqual(self._checks_by_id(service, result["id"])["OUTPUT_EXISTS"]["result"], "FAIL")
        finally:
            store.close()

    def test_checksum_mismatch_finalizes_fail(self):
        store, render = self._copy_proof_store()
        try:
            store.conn.execute("UPDATE render_jobs SET output_checksum_sha256=? WHERE id=?", ("0" * 64, render["id"]))
            store.conn.commit()
            service = QAService(store)
            result = service.execute_qa_run(service.create_qa_run(render["id"])["id"])
            self.assertEqual(result["overall_result"], "FAIL")
            self.assertEqual(self._checks_by_id(service, result["id"])["OUTPUT_CHECKSUM_MATCH"]["result"], "FAIL")
        finally:
            store.close()

    def test_missing_required_audio_finalizes_fail(self):
        store, render = self._copy_proof_store()
        try:
            ffmpeg, _ffprobe = discover_media_tools()
            no_audio = self.root / "no-audio.mp4"
            subprocess.run(
                [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", render["output_path"],
                 "-c:v", "copy", "-an", "-y", str(no_audio)],
                check=True, capture_output=True,
            )
            store.conn.execute(
                "UPDATE render_jobs SET output_path=?, output_checksum_sha256=? WHERE id=?",
                (str(no_audio), sha256_file(no_audio), render["id"]),
            )
            store.conn.commit()
            service = QAService(store)
            result = service.execute_qa_run(service.create_qa_run(render["id"])["id"])
            self.assertEqual(result["overall_result"], "FAIL")
            self.assertEqual(self._checks_by_id(service, result["id"])["REQUIRED_AUDIO_PRESENT"]["result"], "FAIL")
        finally:
            store.close()

    def test_dimension_mismatch_finalizes_fail(self):
        store, render = self._copy_proof_store()
        try:
            store.conn.execute(
                "UPDATE composition_timelines SET target_width=800 WHERE id=?", (render["timeline_id"],)
            )
            store.conn.commit()
            service = QAService(store)
            result = service.execute_qa_run(service.create_qa_run(render["id"])["id"])
            self.assertEqual(result["overall_result"], "FAIL")
            self.assertEqual(self._checks_by_id(service, result["id"])["WIDTH_MATCH"]["result"], "FAIL")
        finally:
            store.close()

    def test_duration_mismatch_finalizes_fail(self):
        store, render = self._copy_proof_store()
        try:
            store.conn.execute(
                "UPDATE composition_timeline_entries SET duration_ms=5000 WHERE timeline_id=?",
                (render["timeline_id"],),
            )
            store.conn.commit()
            service = QAService(store)
            result = service.execute_qa_run(service.create_qa_run(render["id"])["id"])
            self.assertEqual(result["overall_result"], "FAIL")
            self.assertEqual(self._checks_by_id(service, result["id"])["DURATION_WITHIN_TOLERANCE"]["result"], "FAIL")
        finally:
            store.close()

    def test_source_checksum_mismatch_finalizes_fail(self):
        store, render = self._copy_proof_store()
        try:
            evidence = json.loads(render["probe_json"])
            first_key = next(iter(evidence["source_checksums_after"]))
            evidence["source_checksums_after"][first_key] = "0" * 64
            store.conn.execute("UPDATE render_jobs SET probe_json=? WHERE id=?", (json.dumps(evidence), render["id"]))
            store.conn.commit()
            service = QAService(store)
            result = service.execute_qa_run(service.create_qa_run(render["id"])["id"])
            self.assertEqual(result["overall_result"], "FAIL")
            self.assertEqual(self._checks_by_id(service, result["id"])["SOURCE_CHECKSUM_MATCH"]["result"], "FAIL")
        finally:
            store.close()
    def test_artifact_failure_finalizes_fail_not_error(self):
        store, render = self._copy_proof_store()
        try:
            store.conn.execute("UPDATE render_jobs SET output_path=? WHERE id=?", (str(self.root / "missing.mp4"), render["id"]))
            store.conn.commit()
            service = QAService(store)
            result = service.execute_qa_run(service.create_qa_run(render["id"])["id"])
            self.assertEqual(result["lifecycle_state"], "FINALIZED")
            self.assertEqual(result["overall_result"], "FAIL")
            self.assertIsNone(result["error_code"])
        finally:
            store.close()

    def test_review_requires_note(self):
        store, service, finalized = self._run_clean()
        try:
            with self.assertRaises(ValueError):
                service.record_qa_review(finalized["id"], "ACCEPTED", "")
            review = service.get_qa_review(finalized["id"])
            self.assertEqual(review["review_state"], "PENDING")
        finally:
            store.close()

    def test_review_does_not_mutate_automated_evidence(self):
        store, service, finalized = self._run_clean()
        try:
            run_before = dict(service.get_qa_run(finalized["id"]))
            checks_before = service.list_qa_checks(finalized["id"])
            review = service.record_qa_review(finalized["id"], "ACCEPTED", "reviewed and accepted")
            self.assertEqual(review["review_state"], "ACCEPTED")
            self.assertTrue(review["reviewed_at"])
            self.assertEqual(service.get_qa_run(finalized["id"]), run_before)
            self.assertEqual(service.list_qa_checks(finalized["id"]), checks_before)
        finally:
            store.close()

    def test_restart_persistence(self):
        store, service, finalized = self._run_clean()
        db_path = store.db_path
        run_id = finalized["id"]
        checks = service.list_qa_checks(run_id)
        store.close()
        reopened = CreativeOSStore(db_path)
        try:
            service2 = QAService(reopened)
            self.assertEqual(service2.get_qa_run(run_id)["overall_result"], "PASS")
            self.assertEqual(service2.list_qa_checks(run_id), checks)
            self.assertEqual(service2.get_qa_review(run_id)["review_state"], "PENDING")
        finally:
            reopened.close()


if __name__ == "__main__":
    unittest.main()
