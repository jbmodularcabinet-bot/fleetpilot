import tempfile
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.saas_bridge import SaaSBridgeService


OBJECTIVE = "Generate qualified demo and inquiry interest from Philippine trucking and logistics owners."
AUDIENCE = "Philippine trucking and logistics owners/operators managing fleets and delivery operations."
OFFER = "Book a guided FleetPilot demo to see fleet visibility, dispatch control, accountability and trip profitability in one operating system."


class SaaSBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "creativeos.sqlite3"
        self.store = CreativeOSStore(self.db)
        self.assertEqual(self.store.migrate_to_latest(), 13)
        self.service = SaaSBridgeService(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _campaign(self):
        campaign = self.service.create_campaign(
            "FleetPilot Meta Lead Campaign",
            "Create a Meta ad campaign for Philippine trucking/logistics owners that drives qualified demo inquiries.",
        )
        return self.service.update_campaign(
            campaign["id"],
            {
                "objective": OBJECTIVE,
                "audience": AUDIENCE,
                "offer": OFFER,
                "cta": "Book a FleetPilot demo",
                "format": "30s Ad",
                "duration_seconds": 30,
                "aspect_ratio": "1:1",
            },
        )
    def _through_storyboard(self):
        campaign = self._campaign()
        for stage in ("AUDIENCE", "OFFER", "BRAND", "DIRECTOR"):
            self.service.advance_stage(campaign["id"], stage)
        self.service.generate_director(campaign["id"])
        self.service.approve_director(campaign["id"])
        return self.service.get_campaign(campaign["id"])

    def test_campaign_persists_authoritatively(self):
        campaign = self._campaign()
        self.service.advance_stage(campaign["id"], "AUDIENCE")
        campaign_id = campaign["id"]
        self.store.close()
        self.store = CreativeOSStore(self.db)
        self.service = SaaSBridgeService(self.store)
        reloaded = self.service.get_campaign(campaign_id)
        self.assertEqual(reloaded["objective"], OBJECTIVE)
        self.assertEqual(reloaded["duration_seconds"], 30)
        self.assertEqual(reloaded["aspect_ratio"], "1:1")
        self.assertEqual(reloaded["status"], "AUDIENCE")

    def test_required_objective_blocks_progression(self):
        campaign = self.service.create_campaign("Incomplete Campaign")
        with self.assertRaisesRegex(ValueError, "objective"):
            self.service.advance_stage(campaign["id"], "AUDIENCE")

    def test_director_and_storyboard_preserve_duration_and_ratio(self):
        campaign = self._campaign()
        for stage in ("AUDIENCE", "OFFER", "BRAND", "DIRECTOR"):
            self.service.advance_stage(campaign["id"], stage)
        plan = self.service.generate_director(campaign["id"])
        self.assertEqual(
            sum(scene["duration_seconds"] for scene in plan["output_json"]["scene_plan"]),
            30,
        )
        self.service.approve_director(campaign["id"])
        storyboard = self.service.storyboard(campaign["id"])
        self.assertEqual(storyboard["duration_seconds"], 30)
        self.assertEqual(storyboard["campaign_duration_seconds"], 30)
        self.assertEqual(storyboard["aspect_ratio"], "1:1")
    def test_asset_plan_is_campaign_level(self):
        campaign = self._through_storyboard()
        plan = self.service.asset_plan(campaign["id"])
        generated = [item for item in plan["items"] if item["kind"] == "GENERATED"]
        real_ui = [item for item in plan["items"] if item["kind"] == "REAL_UI"]
        self.assertEqual(len(generated), 1)
        self.assertTrue(real_ui)
        self.assertEqual(generated[0]["provider"], "HIGGSFIELD")
        self.assertEqual(generated[0]["model"], "marketing-studio/image")
        self.assertEqual(generated[0]["aspect_ratio"], "1:1")
        self.assertEqual(generated[0]["quantity"], 1)

    def test_generation_request_is_idempotent_and_zero_spend_before_approval(self):
        campaign = self._through_storyboard()
        self.service.asset_plan(campaign["id"])
        first = self.service.ensure_generation_request(campaign["id"])
        second = self.service.ensure_generation_request(campaign["id"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["approval_state"], "COST_APPROVAL_REQUIRED")
        self.assertEqual(first["provider"], "HIGGSFIELD")
        self.assertEqual(first["model"], "marketing-studio/image")
        self.assertEqual(first["estimated_cost_minor"], 190)
        self.assertEqual(first["estimated_cost"], "USD 0.0190")
        self.assertEqual(first["campaign_duration_seconds"], 30)
        self.assertEqual(first["aspect_ratio"], "1:1")
        self.assertEqual(first["provider_submissions"], 0)
        self.assertEqual(first["generation_attempts"], 0)
        self.assertEqual(first["budget_reservations"], 0)
        self.assertEqual(first["spend_events"], 0)
        self.assertEqual(
            self.store.list("generation_spend_ledger", {"request_id": first["id"]}),
            [],
        )
    def test_downstream_governance_is_explicit_before_generation(self):
        campaign = self._through_storyboard()
        governance = self.service.governance(campaign["id"])
        self.assertEqual(governance["automated_qa"], "NOT_GENERATED")
        self.assertEqual(governance["provenance"], "NOT_GENERATED")
        self.assertEqual(governance["human_review"], "NOT_GENERATED")
        self.assertEqual(governance["export"], "NOT_GENERATED")
        self.assertEqual(governance["publishing"], "MANUAL_ONLY")
        self.assertFalse(governance["auto_publish"])


if __name__ == "__main__":
    unittest.main()
