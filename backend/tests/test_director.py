import tempfile
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.director import CampaignBrief, DeterministicMockCreativeDirectorProvider, LiveLLMCreativeDirectorProvider, estimate_cost, validate_brief, validate_output
from creativeos_db.director_service import CreativeDirectorService


def golden_brief() -> CampaignBrief:
    return CampaignBrief(
        brand_profile_id="brand-fleetpilot-golden",
        objective="Create a 60-second FleetPilot explainer for Philippine trucking owners.",
        target_audience="Philippine trucking company owners, managers, dispatchers, operators",
        awareness_level="problem-aware", pain_points=["fragmented operations"],
        core_offer="Operational control, dispatch visibility, trip profitability, accountability",
        cta="See FleetPilot in action", campaign_format="60s Explainer", duration_seconds=60,
        aspect_ratio="16:9", language="English", tone="clear and confident", presenter_mode="none",
        real_ui_percent=85, generated_percent=15, budget_preference="Balanced", quality_preference="High",
        production_constraints=["preserve real FleetPilot UI exactly"])


class DirectorUnitTests(unittest.TestCase):
    def test_brief_validation(self):
        validate_brief(golden_brief())
        bad = golden_brief().__class__(**{**golden_brief().__dict__, "objective": ""})
        with self.assertRaises(ValueError): validate_brief(bad)

    def test_mock_is_deterministic_and_valid(self):
        provider = DeterministicMockCreativeDirectorProvider()
        brand = {"name":"FleetPilot","core_promise":"Fleet control","tagline":"Track. Dispatch. Control. Grow.","default_immutable_ui":True}
        a = provider.generate(golden_brief(), brand); b = provider.generate(golden_brief(), brand)
        self.assertEqual(a, b); validate_output(a); self.assertEqual(len(a["scene_plan"]), 8)

    def test_protected_ui_is_compositing_only(self):
        brand = {"name":"FleetPilot","core_promise":"Fleet control","default_immutable_ui":True}
        plan = DeterministicMockCreativeDirectorProvider().generate(golden_brief(), brand)
        ui = [s for s in plan["scene_plan"] if s["scene_type"] == "REAL_UI"]
        self.assertTrue(ui); self.assertTrue(all(s["recommended_generation_method"] == "COMPOSITING_ONLY" for s in ui))

    def test_cost_estimate_and_live_stub(self):
        self.assertEqual(estimate_cost([{"scene_number":1,"scene_type":"REAL_UI","recommended_generation_method":"COMPOSITING_ONLY"}]), (0,0))
        with self.assertRaises(RuntimeError): LiveLLMCreativeDirectorProvider().generate(golden_brief(), {})

class DirectorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "creativeos.sqlite3"
        self.store = CreativeOSStore(self.db); self.store.migrate_to_latest()
        self.brand = BrandBrainService(self.store).load_fleetpilot_fixture()
        self.campaign = self.store.create("campaigns", {"brand_profile_id": self.brand["id"], "title": "FleetPilot Explainer", "objective": golden_brief().objective, "audience": golden_brief().target_audience, "offer": golden_brief().core_offer, "cta": golden_brief().cta, "format": golden_brief().campaign_format, "duration_seconds":60, "aspect_ratio":"16:9", "tone":golden_brief().tone})
        self.service = CreativeDirectorService(self.store, DeterministicMockCreativeDirectorProvider())

    def tearDown(self):
        self.store.close(); self.tmp.cleanup()

    def test_generate_approve_materialize_and_restart(self):
        draft = self.service.generate_plan(self.campaign["id"], golden_brief(), self.brand)
        self.assertEqual(draft["status"], "DRAFT")
        approved = self.service.approve_plan(draft["id"])
        self.assertEqual(approved["status"], "APPROVED")
        materialized = self.service.materialize_storyboard(draft["id"], "FleetPilot Golden")
        self.assertEqual(len(materialized["scenes"]), 8)
        plan_id = draft["id"]
        self.store.close(); self.store = CreativeOSStore(self.db); self.service = CreativeDirectorService(self.store, DeterministicMockCreativeDirectorProvider())
        reloaded = self.service.get_plan(plan_id)
        self.assertEqual(reloaded["status"], "APPROVED")
        self.assertEqual(len(reloaded["output_json"]["scene_plan"]), 8)

    def test_regeneration_versions_without_overwrite(self):
        first = self.service.generate_plan(self.campaign["id"], golden_brief(), self.brand)
        self.service.approve_plan(first["id"])
        second = self.service.generate_plan(self.campaign["id"], golden_brief(), self.brand)
        self.assertEqual(first["version"], 1); self.assertEqual(second["version"], 2)
        self.assertEqual(self.store.get("director_plans", first["id"])["status"], "APPROVED")

    def test_migration_v2_v3_rollback_reapply_preserves_brand(self):
        brand_id = self.brand["id"]
        self.assertEqual(self.store.schema_version(), 6)
        self.assertEqual(self.store.rollback_to(3), 3)
        self.assertEqual(self.store.get("brand_profiles", brand_id)["name"], "FleetPilot")
        self.assertEqual(self.store.migrate_to_latest(), 6)
        self.assertEqual(self.store.get("brand_profiles", brand_id)["name"], "FleetPilot")


if __name__ == "__main__": unittest.main()
