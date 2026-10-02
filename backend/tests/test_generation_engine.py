import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from creativeos_db import CreativeOSStore
from creativeos_db.brand_service import BrandBrainService
from creativeos_db.generation import GenerationService, DeterministicMockGenerationProvider
from creativeos_db.generation_engine import (
    BudgetGuard,
    GenerationModelRouter,
    GenerationOrchestrator,
    HiggsfieldGenerationWorker,
)
from creativeos_db.higgsfield_provider import (
    HiggsfieldProvider,
    HiggsfieldSubmission,
    HiggsfieldTerminalResult,
)


class FakeHiggsfieldProvider:
    def __init__(self):
        self.submissions = 0

    def submit(self, model_id, input_payload, *, correlation_id, **kwargs):
        self.submissions += 1
        return HiggsfieldSubmission(
            request_id="hf-proof-001",
            status="queued",
            status_url="https://status.example/hf-proof-001",
            cancel_url=None,
            raw={"request_id": "hf-proof-001"},
        )
    def poll(self, submission, *, on_status=None, **kwargs):
        if on_status:
            on_status({"status": "in_progress"})
        return HiggsfieldTerminalResult(
            request_id=submission.request_id,
            status="completed",
            output_url="https://cdn.example/fleetpilot.mp4",
            raw={"status": "completed", "actual_cost_minor": 10200},
        )

    def download(self, url, **kwargs):
        return b"fake-mp4-fleetpilot-proof"


class GenerationEngineV1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "creativeos.sqlite3"
        self.store = CreativeOSStore(self.db)
        self.assertEqual(self.store.migrate_to_latest(), 13)
        self.brand = BrandBrainService(self.store).load_fleetpilot_fixture()
        self.campaign = self.store.create("campaigns", {
            "brand_profile_id": self.brand["id"],
            "title": "FleetPilot Meta Reel",
            "objective": "Lead generation",
            "audience": "Philippine trucking owners",
            "format": "Meta Reel",
            "duration_seconds": 15,
            "aspect_ratio": "9:16",
        })
        board = self.store.create("storyboards", {
            "campaign_id": self.campaign["id"], "title": "FleetPilot Meta Reel"
        })
        self.scene = self.store.create("scenes", {
            "storyboard_id": board["id"],
            "position": 1,
            "title": "Owner visibility",
            "duration_seconds": 15,
            "scene_type": "AI_VIDEO",
            "generation_method": "GENERATIVE",
            "immutable_ui": 0,
        })
        legacy = GenerationService(self.store, DeterministicMockGenerationProvider())
        self.requirement = legacy.create_requirement(self.scene["id"], {
            "asset_type": "video",
            "purpose": "Meta Reel",
            "description": "FleetPilot lead-generation reel",
            "width": 1080,
            "height": 1920,
            "aspect_ratio": "9:16",
            "duration_seconds": 15,
            "priority": "HIGH",
        })
        self.orch = GenerationOrchestrator(self.store)
        BudgetGuard(self.store).set_policy(
            "tenant-fleetpilot", self.campaign["id"],
            campaign_limit_minor=50000,
            tenant_daily_limit_minor=100000,
            approval_required_minor=15000,
            max_attempts=2,
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _draft(self):
        return self.orch.create_request(
            asset_requirement_id=self.requirement["id"],
            tenant_id="tenant-fleetpilot",
            user_id="owner-1",
            idempotency_key="fleetpilot-reel-v1",
            intent="VIDEO_EXPLORATION",
            original_prompt="Create a 15-second FleetPilot Meta Reel for Philippine trucking owners.",
            business_claims=["operational visibility", "trip profitability"],
        )
    def test_current_router_routes_and_costs(self):
        router = GenerationModelRouter()
        static = router.route("STATIC_META", aspect_ratio="9:16")
        self.assertEqual(static.model, "marketing-studio/image")
        self.assertEqual(static.estimated_cost_minor, 190)

        wan = router.route("VIDEO_EXPLORATION", duration_seconds=15)
        self.assertEqual(wan.model, "alibaba/wan-3.0-prime/text-to-video")
        self.assertEqual(wan.estimated_cost_minor, 10200)

        seed = router.route("PREMIUM_FINAL", duration_seconds=15)
        self.assertEqual(seed.model, "bytedance/seedance-2.5/text-to-video")
        self.assertEqual(seed.estimated_cost_minor, 21600)

        seed_ref = router.route("PREMIUM_FINAL", duration_seconds=15, has_references=True)
        self.assertEqual(seed_ref.model, "bytedance/seedance-2.5/reference-to-video")
        self.assertEqual(seed_ref.estimated_cost_minor, 25920)

    def test_claim_guard_and_idempotency(self):
        with self.assertRaises(ValueError):
            self.orch.create_request(
                asset_requirement_id=self.requirement["id"],
                tenant_id="tenant-fleetpilot",
                user_id="owner-1",
                idempotency_key="bad-claim",
                intent="VIDEO_EXPLORATION",
                original_prompt="Make an ad",
                business_claims=["Cuts fuel cost by 40%"],
            )
        first = self._draft()
        again = self._draft()
        self.assertEqual(first["id"], again["id"])
        with self.assertRaises(PermissionError):
            self.orch.get_request(first["id"], "other-tenant")
    def test_budget_lifecycle_and_mocked_provider_provenance(self):
        req = self._draft()
        planned = self.orch.plan(
            req["id"],
            actor="owner-1",
            duration_seconds=15,
            aspect_ratio="9:16",
            script="Know every trip. Know every cost. FleetPilot.",
            storyboard=[{"shot": 1, "duration": 5}, {"shot": 2, "duration": 5}, {"shot": 3, "duration": 5}],
        )
        self.assertEqual(planned["lifecycle_state"], "PLANNED")
        costed = self.orch.cost(req["id"], actor="owner-1")
        self.assertEqual(costed["estimated_cost_minor"], 10200)
        self.assertFalse(bool(costed["approval_required"]))
        approved = self.orch.approve_cost(req["id"], approved_by="owner-1", note="proof budget")
        self.assertEqual(approved["lifecycle_state"], "APPROVED")
        queued = self.orch.queue_request(req["id"], actor="owner-1")
        self.assertEqual(queued["request"]["lifecycle_state"], "QUEUED")

        provider = FakeHiggsfieldProvider()
        worker = HiggsfieldGenerationWorker(
            self.store, provider, Path(self.tmp.name) / "generated", orchestrator=self.orch
        )
        result = worker.execute_request(req["id"])
        self.assertEqual(provider.submissions, 1)
        self.assertEqual(result["provider_request_id"], "hf-proof-001")
        self.assertEqual(self.store.get("generation_requests", req["id"])["lifecycle_state"], "GENERATED")
        prov = self.store.list("generation_provenance", {"request_id": req["id"]})[0]
        self.assertEqual(prov["tenant_id"], "tenant-fleetpilot")
        self.assertEqual(prov["campaign_id"], self.campaign["id"])
        self.assertEqual(prov["model"], "alibaba/wan-3.0-prime/text-to-video")
        self.assertNotIn("credentials", str(prov).lower())
        ledger = self.store.list("generation_spend_ledger", {"request_id": req["id"]})
        self.assertEqual({row["event_type"] for row in ledger}, {"RESERVED", "CHARGED", "RELEASED"})
    def test_premium_route_requires_explicit_premium_approval(self):
        req = self.orch.create_request(
            asset_requirement_id=self.requirement["id"],
            tenant_id="tenant-fleetpilot",
            user_id="owner-1",
            idempotency_key="premium-proof",
            intent="PREMIUM_FINAL",
            original_prompt="Premium FleetPilot final.",
            business_claims=["fleet control"],
        )
        self.orch.plan(req["id"], actor="owner-1", duration_seconds=5, aspect_ratio="9:16")
        self.orch.cost(req["id"], actor="owner-1")
        self.orch.record_approval(
            req["id"], approval_type="BUDGET", approved_by="owner-1", note="budget approved"
        )
        with self.assertRaises(PermissionError):
            self.orch.approve_cost(req["id"], approved_by="owner-1", note="no premium approval")

    def test_server_secret_boundary(self):
        provider = HiggsfieldProvider("id:super-secret")
        self.assertNotIn("super-secret", repr(provider))
        self.assertNotIn("super-secret", str(provider.__dict__.keys()))
        old_a, old_b = os.environ.get("HF_CREDENTIALS"), os.environ.get("HF_KEY")
        try:
            os.environ.pop("HF_CREDENTIALS", None)
            os.environ.pop("HF_KEY", None)
            with self.assertRaises(RuntimeError):
                HiggsfieldProvider.from_env()
        finally:
            if old_a is not None:
                os.environ["HF_CREDENTIALS"] = old_a
            if old_b is not None:
                os.environ["HF_KEY"] = old_b

    def test_v9_v10_rollback_reapply(self):
        request_id = self._draft()["id"]
        self.assertEqual(self.store.rollback_to(9), 9)
        self.assertEqual(self.store.migrate_to_latest(), 13)
        with self.assertRaises(KeyError):
            self.store.get("generation_requests", request_id)

    def test_default_transport_uses_httpx_contract(self):
        context = MagicMock()
        client = context.__enter__.return_value
        client.request.return_value = MagicMock(
            status_code=403,
            headers={"X-Test": "1"},
            content=b'{"detail":"blocked"}',
        )
        provider = HiggsfieldProvider("id:secret")
        with patch("creativeos_db.higgsfield_provider.httpx.Client", return_value=context):
            status, headers, raw = provider._default_transport(
                "POST",
                "https://api.higgsfield.ai/marketing-studio/image",
                provider._headers("corr-1"),
                b"{}",
                5.0,
            )
        self.assertEqual(status, 403)
        self.assertEqual(headers["X-Test"], "1")
        self.assertEqual(raw, b'{"detail":"blocked"}')
        client.request.assert_called_once()

    def test_provider_poll_keeps_server_authorization(self):
        seen = {}
        def transport(method, url, headers, body, timeout):
            seen.update(headers)
            return 200, {}, b'{"status":"completed","video":{"url":"https://cdn.example/out.mp4"}}'
        provider = HiggsfieldProvider("id:secret", transport=transport, sleep_fn=lambda _: None)
        result = provider.poll(HiggsfieldSubmission(
            request_id="req-1",
            status="queued",
            status_url="https://api.higgsfield.ai/requests/req-1/status",
            cancel_url=None,
            raw={},
        ))
        self.assertEqual(result.status, "completed")
        self.assertEqual(seen.get("Authorization"), "Key id:secret")
        self.assertEqual(seen.get("User-Agent"), "CreativeOS/1.0")


if __name__ == "__main__":
    unittest.main()
