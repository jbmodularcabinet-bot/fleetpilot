"""Isolation regressions exercise real SQLite and the existing production services."""
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.multibrand import MultiBrandService
from creativeos_db.director import DeterministicMockCreativeDirectorProvider
from creativeos_db.director_service import CreativeDirectorService
from creativeos_db.generation_engine import GenerationOrchestrator
from creativeos_db.queue import GenerationQueueService
from test_director import golden_brief


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "isolation.db"
        self.store = CreativeOSStore(self.db)
        self.store.migrate_to_latest()
        multi = MultiBrandService(self.store)
        self.stacks = []
        for org_id in ("native", "external"):
            multi.create_organization(org_id, org_id, organization_id=org_id,
                                      classification="NATIVE" if org_id == "native" else "EXTERNAL",
                                      ecosystem_key="habi" if org_id == "native" else "")
            for n in range(2):
                brand = multi.create_brand(org_id, {"name": f"{org_id}-{n}", "core_promise": f"{org_id}-{n} promise"})
                campaign = multi.create_campaign(org_id, brand["id"], {"title": brand["name"]})
                board = self.store.create("storyboards", {"campaign_id": campaign["id"], "title": "board"})
                scene = self.store.create("scenes", {"storyboard_id": board["id"], "position": 1,
                                                   "title": "scene", "scene_type": "GENERATED"})
                req = self.store.create("asset_requirements", {"scene_id": scene["id"], "asset_type": "image"})
                job = self.store.create("generation_jobs", {"scene_id": scene["id"],
                    "asset_requirement_id": req["id"], "provider": "MOCK", "model": "image"})
                request = GenerationOrchestrator(self.store).create_request(
                    asset_requirement_id=req["id"], tenant_id=org_id, user_id="owner",
                    idempotency_key=brand["id"], intent="STATIC_META", original_prompt=brand["name"])
                self.stacks.append(dict(org=org_id, brand=brand, campaign=campaign,
                                        board=board, scene=scene, req=req, job=job, request=request))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_mixed_asset_links_rejected_within_and_across_organizations(self):
        a = self.stacks[0]
        for b in self.stacks[1:]:
            with self.subTest(other=b["brand"]["name"]):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.store.create("assets", {"campaign_id": a["campaign"]["id"],
                        "scene_id": b["scene"]["id"], "asset_type": "image", "path": "local.png"})

    def test_cost_and_generation_lineage_rejected(self):
        a, b = self.stacks[:2]
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create("cost_recommendations", {
                "campaign_id": a["campaign"]["id"], "asset_requirement_id": b["req"]["id"]})
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create("generated_assets", {"generation_job_id": a["job"]["id"],
                "asset_requirement_id": b["req"]["id"], "output_path": "mock://result",
                "output_type": "image", "prompt_snapshot": "", "provider_snapshot": "MOCK",
                "model_snapshot": "image", "checksum_sha256": "0" * 64})

    def test_cannot_reparent_history_to_another_brand(self):
        a, b = self.stacks[:2]
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.update("campaigns", a["campaign"]["id"], {"brand_profile_id": b["brand"]["id"]})
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.update("storyboards", a["board"]["id"], {"campaign_id": b["campaign"]["id"]})

    def test_director_uses_persisted_brand_even_if_caller_spoofs_content(self):
        a, b = self.stacks[:2]
        brief = replace(golden_brief(), brand_profile_id=a["brand"]["id"])
        forged = dict(b["brand"], id=a["brand"]["id"], core_promise="FOREIGN BRAND POISON")
        plan = CreativeDirectorService(self.store, DeterministicMockCreativeDirectorProvider()).generate_plan(
            a["campaign"]["id"], brief, forged)
        self.assertNotIn("FOREIGN BRAND POISON", json.dumps(plan))
        self.assertIn(a["brand"]["name"], json.dumps(plan))

    def test_scoped_crud_filters_lists_and_rejects_foreign_ids_without_mutation(self):
        a = self.stacks[0]
        with CreativeOSStore(self.db, organization_id=a["org"], brand_profile_id=a["brand"]["id"]) as scoped:
            self.assertEqual([r["id"] for r in scoped.list("campaigns")], [a["campaign"]["id"]])
            for b in self.stacks[1:]:
                for table, key in (("brand_profiles", "brand"), ("campaigns", "campaign"),
                                   ("generation_requests", "request"), ("generation_jobs", "job")):
                    with self.subTest(table=table, other=b["brand"]["name"]):
                        with self.assertRaises(PermissionError):
                            scoped.get(table, b[key]["id"])
                with self.assertRaises(PermissionError):
                    scoped.update("campaigns", b["campaign"]["id"], {"title": "poison"})
                with self.assertRaises(PermissionError):
                    scoped.delete("campaigns", b["campaign"]["id"])
                with self.assertRaises(PermissionError):
                    scoped.create("assets", {"campaign_id": b["campaign"]["id"],
                        "asset_type": "image", "path": "poison.png"})
            self.assertFalse(self.store.list("assets"))
            self.assertTrue(all(self.store.get("campaigns", s["campaign"]["id"])["title"] != "poison"
                                for s in self.stacks))

    def test_scoped_queue_never_claims_foreign_work(self):
        a, b = self.stacks[:2]
        queue = GenerationQueueService(self.store)
        foreign = queue.enqueue(b["job"]["id"], priority=1)
        own = queue.enqueue(a["job"]["id"], priority=100)
        with CreativeOSStore(self.db, organization_id=a["org"], brand_profile_id=a["brand"]["id"]) as scoped:
            service = GenerationQueueService(scoped)
            with self.assertRaises(PermissionError):
                service.claim_job(b["job"]["id"], "scoped-worker")
            claimed = service.claim_next("scoped-worker")
            self.assertEqual(claimed["id"], own["id"])
            self.assertIsNone(service.claim_next("scoped-worker"))
        self.assertEqual(self.store.get("generation_queue", foreign["id"])["state"], "QUEUED")

    def test_legacy_data_excluded_and_nonempty_rollback_refused_atomically(self):
        brand = self.store.create("brand_profiles", {"name": "legacy"})
        campaign = self.store.create("campaigns", {"brand_profile_id": brand["id"], "title": "legacy"})
        a = self.stacks[0]
        with CreativeOSStore(self.db, organization_id=a["org"], brand_profile_id=a["brand"]["id"]) as scoped:
            with self.assertRaises(PermissionError):
                scoped.get("campaigns", campaign["id"])
            with self.assertRaises(PermissionError):
                scoped.rollback_to(10)
        with self.assertRaises(ValueError):
            self.store.rollback_to(10)
        self.assertEqual(self.store.schema_version(), 11)
        self.assertEqual(len(self.store.list("organizations")), 2)
        self.assertEqual(self.store.foreign_key_violations(), [])

    def test_generation_core_does_not_import_higgsfield_adapter(self):
        import subprocess
        import sys
        code = ("import sys; import creativeos_db.generation_engine; "
                "assert 'creativeos_db.higgsfield_provider' not in sys.modules")
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_scoped_external_generation_qa_review_export_without_higgsfield(self):
        from creativeos_db.generation_engine import (
            BudgetGuard, ProviderGenerationWorker, GenerationReleaseGate, RouteDecision)
        from creativeos_db.provider_contract import ProviderSubmission, ProviderResult
        from creativeos_db.composition import CompositionService, discover_media_tools
        from creativeos_db.qa import QAService
        from creativeos_db.voice import VoiceService

        class LocalRouter:
            def route(self, intent, **kwargs):
                return RouteDecision(provider="LOCAL_TEST", model="fixture-image", capability="image",
                    intent=intent, settings={}, estimated_cost_minor=10, cost_source="TEST_FIXTURE")
            def provider_input(self, route, prompt, references):
                return {"prompt": prompt}

        class LocalProvider:
            def submit(self, model_id, payload, **kwargs):
                return ProviderSubmission("local-proof", "queued", "local://status", None, {})
            def poll(self, submission, **kwargs):
                return ProviderResult(submission.request_id, "completed", "local://hero",
                                      {"actual_cost_minor": 10})
            def download(self, url):
                return (Path(__file__).resolve().parents[2] / "app/src/assets/hero.png").read_bytes()

        a = self.stacks[2]
        output = Path(self.tmp.name)
        with CreativeOSStore(self.db, organization_id=a["org"], brand_profile_id=a["brand"]["id"]) as scoped:
            director = CreativeDirectorService(scoped, DeterministicMockCreativeDirectorProvider())
            brief = replace(golden_brief(), brand_profile_id=a["brand"]["id"],
                            objective="Explain Client Cloud", target_audience="Small teams",
                            core_offer=a["brand"]["core_promise"], cta="Try Client Cloud",
                            production_constraints=[])
            plan = director.generate_plan_for_campaign(a["campaign"]["id"], brief)
            self.assertNotIn("habi", plan["output_json"].lower())
            director.approve_plan(plan["id"])
            board = director.materialize_storyboard(plan["id"], "Client Cloud")["storyboard"]
            scene = scoped.list("scenes", {"storyboard_id": board["id"]})[0]
            requirement = scoped.create("asset_requirements", {"scene_id": scene["id"], "asset_type": "image"})
            orch = GenerationOrchestrator(scoped, model_router=LocalRouter())
            BudgetGuard(scoped).set_policy(a["org"], a["campaign"]["id"],
                campaign_limit_minor=1000, tenant_daily_limit_minor=2000, approval_required_minor=500)
            req = orch.create_request(asset_requirement_id=requirement["id"], tenant_id=a["org"],
                user_id="owner", idempotency_key="local-proof", intent="STATIC_META",
                original_prompt="Client Cloud artwork")
            orch.plan(req["id"], actor="owner", aspect_ratio="16:9", duration_seconds=2)
            orch.cost(req["id"], actor="owner")
            orch.approve_cost(req["id"], approved_by="owner", note="Approved test budget")
            orch.queue_request(req["id"], actor="owner")
            result = ProviderGenerationWorker(scoped, LocalProvider(), output / "generated",
                                              orchestrator=orch).execute_request(req["id"])
            self.assertEqual(scoped.list("generation_provenance", {"request_id": req["id"]})[0]["provider"],
                             "LOCAL_TEST")
            voice_service = VoiceService(scoped, output / "voice")
            voice = voice_service.run_job(voice_service.create_job(
                scene["id"], "Client Cloud makes work clear", "en", "mock-ainsley")["id"])
            ffmpeg, ffprobe = discover_media_tools()
            composer = CompositionService(scoped, output, output / "rendered", ffmpeg, ffprobe)
            timeline = composer.create_timeline(a["campaign"]["id"], board["id"], [{
                "scene_id": scene["id"], "duration_ms": 2000,
                "visual_path": result["local_path"], "audio_path": voice["output_path"],
            }])["timeline"]
            render = composer.render_preview(timeline["id"])
            self.assertEqual(render["status"], "SUCCEEDED")
            qa_service = QAService(scoped, ffprobe)
            qa = qa_service.execute_qa_run(qa_service.create_qa_run(render["id"])["id"])
            self.assertEqual(qa["overall_result"], "PASS", qa)
            self.assertEqual(qa["actual_check_count"], 11)
            qa_service.record_qa_review(qa["id"], "ACCEPTED", "Reviewed test render")
            orch.begin_qa(req["id"], actor="owner")
            self.assertEqual(GenerationReleaseGate(scoped).run(req["id"], render_qa_run_id=qa["id"])["result"], "PASS")
            orch.complete_qa(req["id"], actor="owner")
            with self.assertRaises(PermissionError):
                orch.create_export(req["id"], render_job_id=render["id"], qa_run_id=qa["id"], actor="owner")
            orch.human_approve(req["id"], approved_by="owner", note="Approved local proof")
            exported = orch.create_export(req["id"], render_job_id=render["id"], qa_run_id=qa["id"], actor="owner")["export"]
            self.assertEqual(exported["campaign_id"], a["campaign"]["id"])
            self.assertEqual(scoped.get("generation_requests", req["id"])["lifecycle_state"], "READY_FOR_EXPORT")
            self.assertEqual(scoped.foreign_key_violations(), [])
        b = self.stacks[3]
        with CreativeOSStore(self.db, organization_id=b["org"], brand_profile_id=b["brand"]["id"]) as other:
            for table, row_id in (("render_jobs", render["id"]), ("qa_runs", qa["id"]),
                                  ("export_jobs", exported["id"]), ("generation_requests", req["id"])):
                with self.assertRaises(PermissionError):
                    other.get(table, row_id)
            self.assertEqual(other.list("generation_provenance"), [])

    def test_all_owned_tables_have_scope_maps(self):
        from creativeos_db.store import TABLES
        from creativeos_db.scope_schema import GLOBAL_TABLES, SCOPED_TABLES
        self.assertEqual(TABLES, SCOPED_TABLES | GLOBAL_TABLES | {"organizations"})

    def test_failed_migration_leaves_v10_data_and_schema_unchanged(self):
        from unittest.mock import patch
        from creativeos_db.migrations import MIGRATIONS
        with CreativeOSStore(Path(self.tmp.name) / "migration.db") as old:
            old.migrate_to_latest()
            old.rollback_to(10)
            brand = old.create("brand_profiles", {"name": "Legacy upgrade"})
            original = dict(brand)
            broken = (MIGRATIONS[11][0] + "; SELECT * FROM nonexistent_table;", MIGRATIONS[11][1])
            with patch.dict(MIGRATIONS, {11: broken}):
                with self.assertRaises(sqlite3.OperationalError):
                    old.migrate_to_latest()
            self.assertEqual(old.schema_version(), 10)
            self.assertEqual(old.get("brand_profiles", brand["id"]), original)
            self.assertNotIn("organization_id", old._columns("brand_profiles"))
            self.assertEqual(old.migrate_to_latest(), 11)
            self.assertEqual(old.foreign_key_violations(), [])

    def test_scoped_governance_rejects_other_brand_before_any_write(self):
        a, b = self.stacks[:2]
        with CreativeOSStore(self.db, organization_id=a["org"], brand_profile_id=a["brand"]["id"]) as scoped:
            orch = GenerationOrchestrator(scoped)
            with self.assertRaises(PermissionError):
                orch.record_approval(b["request"]["id"], approval_type="BUDGET",
                                     approved_by="wrong-brand", note="invalid")
            with self.assertRaises(PermissionError):
                orch.plan(b["request"]["id"], actor="wrong-brand")
            with self.assertRaises(PermissionError):
                orch._advance(b["request"]["id"], "wrong-brand")
        self.assertEqual(self.store.list("generation_approvals"), [])
        self.assertEqual(self.store.get("generation_requests", b["request"]["id"])["lifecycle_step"], 0)

    def test_database_rejects_forged_spend_ownership(self):
        a, b = self.stacks[:2]
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create("generation_spend_ledger", {
                "request_id": a["request"]["id"], "tenant_id": a["org"],
                "campaign_id": b["campaign"]["id"], "event_type": "RESERVED",
                "amount_minor": 1, "currency": "USD", "spend_date": "2026-09-30"})
        self.assertEqual(self.store.list("generation_spend_ledger"), [])

    def _render_record(self, stack):
        timeline = self.store.create("composition_timelines", {
            "campaign_id": stack["campaign"]["id"], "storyboard_id": stack["board"]["id"],
            "target_width": 640, "target_height": 360, "aspect_ratio": "16:9", "fps": 24})
        return self.store.create("render_jobs", {
            "timeline_id": timeline["id"], "render_identity": timeline["id"],
            "status": "SUCCEEDED", "output_path": "test-only.mp4",
            "ffmpeg_path": "test-only", "ffmpeg_version": "test-only"})

    def test_foreign_render_cannot_authorize_release_or_export(self):
        from creativeos_db.generation_engine import GenerationReleaseGate
        from creativeos_db.qa import QAService
        a, b = self.stacks[:2]
        render = self._render_record(b)
        qa = QAService(self.store).create_qa_run(render["id"])
        orch = GenerationOrchestrator(self.store)
        self.store.update("generation_requests", a["request"]["id"],
                          {"lifecycle_step": 7, "lifecycle_state": "QA"})
        with self.assertRaisesRegex(PermissionError, "another campaign"):
            GenerationReleaseGate(self.store).run(a["request"]["id"], render_qa_run_id=qa["id"])
        self.store.update("generation_requests", a["request"]["id"],
                          {"lifecycle_step": 9, "lifecycle_state": "APPROVED"})
        with self.assertRaisesRegex(PermissionError, "another campaign"):
            orch.create_export(a["request"]["id"], render_job_id=render["id"],
                               qa_run_id=qa["id"], actor="owner")
        self.assertEqual(self.store.list("export_jobs"), [])
        self.assertEqual(self.store.list("generation_gate_runs"), [])

    def test_scoped_qa_retry_does_not_write_foreign_run(self):
        from creativeos_db.qa import QAService
        a, b = self.stacks[:2]
        render = self._render_record(b)
        qa = QAService(self.store).create_qa_run(render["id"])
        self.store.conn.execute("UPDATE qa_runs SET lifecycle_state='ERROR' WHERE id=?", (qa["id"],))
        self.store.conn.commit()
        with CreativeOSStore(self.db, organization_id=a["org"], brand_profile_id=a["brand"]["id"]) as scoped:
            with self.assertRaises(PermissionError):
                QAService(scoped).retry_error_qa_run(qa["id"])
        self.assertEqual(len(self.store.list("qa_runs")), 1)

    def test_scoped_stale_recovery_leaves_foreign_queue_unchanged(self):
        from datetime import datetime, timedelta, timezone
        a, b = self.stacks[:2]
        queue = GenerationQueueService(self.store)
        row = queue.enqueue(b["job"]["id"])
        queue.claim_job(b["job"]["id"], "foreign-worker", lease_seconds=1)
        with CreativeOSStore(self.db, organization_id=a["org"], brand_profile_id=a["brand"]["id"]) as scoped:
            self.assertEqual(GenerationQueueService(scoped).recover_stale(
                datetime.now(timezone.utc) + timedelta(minutes=5)), [])
        self.assertEqual(self.store.get("generation_queue", row["id"])["state"], "CLAIMED")


if __name__ == "__main__":
    unittest.main()
