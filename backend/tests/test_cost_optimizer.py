import tempfile
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.cost_optimizer import CostOptimizer
from creativeos_db.generation import DeterministicMockGenerationProvider
from creativeos_db.queue import GenerationQueueService
from creativeos_db.router import ProviderRegistration, ProviderRouter


def router_with(*names):
    router = ProviderRouter()
    for name in names:
        router.register(ProviderRegistration(
            name, frozenset({"image", "video", "presenter", "voice"}),
            DeterministicMockGenerationProvider(), True
        ))
    router.register(ProviderRegistration("DISABLED", frozenset({"image"}), None, False))
    return router


class Batch8CostOptimizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "creativeos.sqlite3"
        self.store = CreativeOSStore(self.db)
        self.assertEqual(self.store.migrate_to_latest(), 11)
        brand = BrandBrainService(self.store).load_fleetpilot_fixture()
        self.campaign = self.store.create("campaigns", {"brand_profile_id": brand["id"], "title": "Cost"})
        board = self.store.create("storyboards", {"campaign_id": self.campaign["id"], "title": "Cost"})
        self.scene = self.store.create("scenes", {
            "storyboard_id": board["id"], "position": 1, "title": "Shot",
            "duration_seconds": 5, "scene_type": "AI_IMAGE", "generation_method": "GENERATIVE",
        })
        self.router = router_with("A", "B", "MOCK")
        self.opt = CostOptimizer(self.store, self.router)
        self.req = self.store.create("asset_requirements", {
            "scene_id": self.scene["id"], "asset_type": "image", "purpose": "hero",
            "duration_seconds": 5,
        })

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def profile(self, provider="A", model="m1", currency="PHP", exp=2,
                fixed=None, image=None, second=None, unit=None, quality="HIGH", version=1):
        return self.opt.create_profile({
            "provider": provider, "model": model, "capability": "image",
            "quality_tier": quality, "currency": currency,
            "currency_minor_exponent": exp, "fixed_cost_minor": fixed,
            "per_image_cost_minor": image, "per_second_cost_minor": second,
            "per_unit_cost_minor": unit, "version": version,
            "effective_at": "2026-09-22T00:00:00+00:00", "source_label": "LOCAL_CONFIG",
        })
    def budget(self, total=10000, currency="PHP", exp=2, near=9000):
        return self.opt.set_campaign_budget(self.campaign["id"], total, currency, exp, near)

    def test_v6_v7_rollback_reapply_preserves_queue_job(self):
        job = self.store.create("generation_jobs", {
            "scene_id": self.scene["id"], "asset_requirement_id": self.req["id"],
            "provider": "MOCK", "model": "m", "prompt": "x",
        })
        queue = GenerationQueueService(self.store).enqueue(job["id"])
        self.assertEqual(self.store.rollback_to(6), 6)
        self.assertEqual(self.store.get("generation_jobs", job["id"])["id"], job["id"])
        self.assertEqual(self.store.get("generation_queue", queue["id"])["id"], queue["id"])
        self.assertEqual(self.store.migrate_to_latest(), 11)

    def test_money_is_integer_minor_units_and_zero_is_known(self):
        with self.assertRaises(ValueError):
            self.profile(fixed=1.25)
        self.budget()
        self.profile(fixed=0)
        result = self.opt.recommend(self.req["id"], "HIGH")
        est = result["estimates"][0]
        self.assertEqual(est["original_cost_minor"], 0)
        self.assertEqual(est["normalized_cost_minor"], 0)
        self.assertEqual(est["budget_state"], "WITHIN_BUDGET")
    def test_missing_campaign_budget_is_unknown_without_currency_inference(self):
        self.profile(fixed=500)
        est = self.opt.recommend(self.req["id"], "HIGH")["estimates"][0]
        self.assertEqual(est["original_cost_minor"], 500)
        self.assertIsNone(est["normalized_cost_minor"])
        self.assertEqual(est["budget_state"], "UNKNOWN")
        self.assertEqual(est["is_recommended"], 0)

    def test_combined_pricing_components_are_exact(self):
        self.budget(total=10000)
        self.profile(fixed=100, image=10, second=2, unit=5)
        est = self.opt.recommend(self.req["id"], "HIGH", image_count=2, unit_count=3)["estimates"][0]
        self.assertEqual(est["original_cost_minor"], 145)
        self.assertEqual(est["normalized_cost_minor"], 145)
        self.assertIn('"total_original_minor": 145', est["calculation_json"])

    def test_unknown_pricing_never_becomes_zero(self):
        self.budget()
        self.profile(fixed=None, image=None, second=None, unit=None)
        est = self.opt.recommend(self.req["id"], "HIGH")["estimates"][0]
        self.assertIsNone(est["original_cost_minor"])
        self.assertIsNone(est["normalized_cost_minor"])
        self.assertEqual(est["budget_state"], "UNKNOWN")
        self.assertEqual(est["is_recommended"], 0)

    def test_same_currency_budget_rollup_and_threshold(self):
        self.budget(total=10000, near=9000)
        self.profile(provider="A", model="within", fixed=3000)
        self.profile(provider="B", model="near", fixed=4000)
        result = self.opt.recommend(
            self.req["id"], "HIGH", committed_cost_minor=2000, planned_cost_minor=3000
        )
        by_model = {e["model"]: e for e in result["estimates"]}
        self.assertEqual(by_model["within"]["budget_state"], "WITHIN_BUDGET")
        self.assertEqual(by_model["near"]["budget_state"], "NEAR_LIMIT")
        self.assertEqual(by_model["near"]["normalized_cost_minor"], 4000)
        self.assertEqual(sum(e["is_recommended"] for e in result["estimates"]), 1)
        self.assertEqual(by_model["within"]["is_recommended"], 1)
    def test_over_budget_is_not_auto_selected(self):
        self.budget(total=10000)
        self.profile(fixed=10001)
        est = self.opt.recommend(self.req["id"], "HIGH")["estimates"][0]
        self.assertEqual(est["budget_state"], "OVER_BUDGET")
        self.assertEqual(est["is_recommended"], 0)

    def test_missing_fx_is_unknown_and_not_cheapest(self):
        self.budget(total=10000, currency="PHP", exp=2)
        self.profile(provider="A", model="usd", currency="USD", exp=2, fixed=1)
        self.profile(provider="B", model="php", currency="PHP", exp=2, fixed=500)
        result = self.opt.recommend(self.req["id"], "HIGH")
        by_model = {e["model"]: e for e in result["estimates"]}
        self.assertEqual(by_model["usd"]["budget_state"], "UNKNOWN")
        self.assertIsNone(by_model["usd"]["normalized_cost_minor"])
        self.assertEqual(by_model["php"]["is_recommended"], 1)

    def test_cross_currency_half_up_and_snapshot_evidence(self):
        self.budget(total=10000, currency="PHP", exp=2)
        self.profile(provider="A", model="usd", currency="USD", exp=2, fixed=1)
        fx = self.opt.create_fx_snapshot({
            "from_currency": "USD", "to_currency": "PHP",
            "from_minor_exponent": 2, "to_minor_exponent": 2,
            "rate_decimal": "1.5", "rate_source": "TEST_SNAPSHOT",
            "rate_effective_at": "2026-09-22T00:00:00+00:00",
            "captured_at": "2026-09-22T00:01:00+00:00",
        })
        est = self.opt.recommend(
            self.req["id"], "HIGH", fx_snapshot_ids={("USD", "PHP"): fx["id"]}
        )["estimates"][0]
        self.assertEqual(est["normalized_cost_minor"], 2)
        self.assertIn("TEST_SNAPSHOT", est["fx_snapshot_json"])
        self.assertEqual(est["normalized_currency"], "PHP")

    def test_provider_and_quality_constraints_win_over_price(self):
        self.budget()
        self.profile(provider="DISABLED", model="cheap", fixed=1)
        self.profile(provider="A", model="wrong-quality", fixed=1, quality="LOW", version=1)
        self.profile(provider="B", model="valid", fixed=500)
        result = self.opt.recommend(self.req["id"], "HIGH")
        self.assertEqual([e["model"] for e in result["estimates"]], ["valid"])
        self.assertEqual(result["estimates"][0]["is_recommended"], 1)
    def test_immutable_ui_blocks_generative_cost_route(self):
        self.budget()
        self.profile(fixed=100)
        self.store.update("scenes", self.scene["id"], {"immutable_ui": 1, "generation_method": "COMPOSITING_ONLY"})
        result = self.opt.recommend(self.req["id"], "HIGH")
        self.assertEqual(result["estimates"], [])

    def test_override_requires_reason_and_preserves_evidence(self):
        self.budget(total=10000)
        self.profile(provider="A", model="a", fixed=1000)
        self.profile(provider="B", model="b", fixed=11000)
        result = self.opt.recommend(self.req["id"], "HIGH")
        over = next(e for e in result["estimates"] if e["model"] == "b")
        with self.assertRaises(ValueError):
            self.opt.record_override(result["recommendation"]["id"], over["id"], "")
        override = self.opt.record_override(
            result["recommendation"]["id"], over["id"], "Client explicitly approved premium route"
        )
        self.assertIn("OVER_BUDGET", override["evidence_json"])
        self.assertEqual(override["reason"], "Client explicitly approved premium route")
    def test_snapshot_persistence_and_immutability(self):
        self.budget()
        profile = self.profile(fixed=1200)
        result = self.opt.recommend(self.req["id"], "HIGH")
        rec_id = result["recommendation"]["id"]
        est_id = result["estimates"][0]["id"]
        self.store.close()
        self.store = CreativeOSStore(self.db)
        self.opt = CostOptimizer(self.store, self.router)
        snap = self.opt.recommendation_snapshot(rec_id)
        self.assertEqual(snap["estimates"][0]["id"], est_id)
        with self.assertRaises(ValueError):
            self.store.update("provider_cost_profiles", profile["id"], {"fixed_cost_minor": 1})
        with self.assertRaises(ValueError):
            self.store.update("cost_estimates", est_id, {"budget_state": "UNKNOWN"})
        with self.assertRaises(ValueError):
            self.store.delete("cost_recommendations", rec_id)


if __name__ == "__main__":
    unittest.main()
