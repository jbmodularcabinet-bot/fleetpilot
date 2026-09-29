from __future__ import annotations

import json
from typing import Any

from .brand_service import BrandBrainService
from .director import CampaignBrief, DeterministicMockCreativeDirectorProvider
from .director_service import CreativeDirectorService
from .generation import DeterministicMockGenerationProvider, GenerationService
from .generation_engine import BudgetGuard, GenerationOrchestrator
from .store import CreativeOSStore


WORKFLOW_STAGES = (
    "OBJECTIVE",
    "AUDIENCE",
    "OFFER",
    "BRAND",
    "DIRECTOR",
    "SCRIPT",
    "STORYBOARD",
    "ASSET_PLAN",
    "GENERATION_REQUEST",
    "COST_APPROVAL_REQUIRED",
)

TENANT_ID = "tenant-fleetpilot"
USER_ID = "local-owner"
CAMPAIGN_ASSET_PURPOSE = "FleetPilot Meta lead-generation campaign creative"


def _decode(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def _money(minor: int | None, exponent: int | None, currency: str | None) -> str | None:
    if minor is None or exponent is None or not currency:
        return None
    return f"{currency} {int(minor) / (10 ** int(exponent)):.4f}"
class SaaSBridgeService:
    def __init__(self, store: CreativeOSStore):
        self.store = store
        self.brands = BrandBrainService(store)
        self.director = CreativeDirectorService(
            store, DeterministicMockCreativeDirectorProvider()
        )
        self.orchestrator = GenerationOrchestrator(store)

    def list_campaigns(self) -> list[dict[str, Any]]:
        rows = self.store.list("campaigns")
        return sorted(rows, key=lambda row: row["updated_at"], reverse=True)

    def create_campaign(self, title: str, objective: str = "") -> dict[str, Any]:
        title = str(title or "").strip()
        if not title:
            raise ValueError("campaign title is required")
        brand = self.brands.load_fleetpilot_fixture()
        existing = [
            row for row in self.store.list(
                "campaigns", {"brand_profile_id": brand["id"]}
            )
            if row["title"].casefold() == title.casefold()
        ]
        if existing:
            return sorted(existing, key=lambda row: row["updated_at"])[-1]
        return self.store.create(
            "campaigns",
            {
                "brand_profile_id": brand["id"],
                "title": title,
                "objective": str(objective or "").strip(),
                "audience": "",
                "offer": "",
                "cta": "Book a FleetPilot demo",
                "format": "30s Ad",
                "duration_seconds": 30,
                "aspect_ratio": "1:1",
                "tone": "clear, operational, credible",
                "status": "OBJECTIVE",
            },
        )

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        return self.store.get("campaigns", campaign_id)

    def update_campaign(
        self, campaign_id: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        allowed = {
            "title", "objective", "audience", "offer", "cta", "format",
            "duration_seconds", "aspect_ratio", "tone",
        }
        data = {key: value for key, value in values.items() if key in allowed}
        if "duration_seconds" in data:
            duration = int(data["duration_seconds"])
            if duration <= 0 or duration > 600:
                raise ValueError("duration must be between 1 and 600 seconds")
            data["duration_seconds"] = duration
        if "aspect_ratio" in data and data["aspect_ratio"] not in {"16:9", "9:16", "1:1"}:
            raise ValueError("unsupported aspect ratio")
        return self.store.update("campaigns", campaign_id, data)
    def advance_stage(self, campaign_id: str, stage: str) -> dict[str, Any]:
        stage = str(stage or "").upper().strip()
        if stage not in WORKFLOW_STAGES:
            raise ValueError("unsupported workflow stage")
        campaign = self.get_campaign(campaign_id)
        required: dict[str, tuple[str, ...]] = {
            "AUDIENCE": ("objective",),
            "OFFER": ("objective", "audience"),
            "BRAND": ("objective", "audience", "offer"),
            "DIRECTOR": ("objective", "audience", "offer"),
            "SCRIPT": ("objective", "audience", "offer"),
            "STORYBOARD": ("objective", "audience", "offer"),
            "ASSET_PLAN": ("objective", "audience", "offer"),
            "GENERATION_REQUEST": ("objective", "audience", "offer"),
            "COST_APPROVAL_REQUIRED": ("objective", "audience", "offer"),
        }
        missing = [
            field for field in required.get(stage, ())
            if not str(campaign.get(field) or "").strip()
        ]
        if missing:
            raise ValueError("required campaign fields missing: " + ", ".join(missing))
        return self.store.update("campaigns", campaign_id, {"status": stage})

    def brand(self, campaign_id: str) -> dict[str, Any]:
        campaign = self.get_campaign(campaign_id)
        return self.brands.get(campaign["brand_profile_id"])

    def _brief(self, campaign: dict[str, Any]) -> CampaignBrief:
        return CampaignBrief(
            brand_profile_id=campaign["brand_profile_id"],
            objective=campaign["objective"],
            target_audience=campaign["audience"],
            awareness_level="problem-aware",
            pain_points=[
                "fuel leakage", "dispatch confusion", "downtime",
                "late deliveries", "driver accountability",
                "unclear trip profitability", "collections",
            ],
            core_offer=campaign["offer"],
            cta=campaign["cta"] or "Book a FleetPilot demo",
            campaign_format=campaign["format"] or "30s Ad",
            duration_seconds=int(campaign["duration_seconds"]),
            aspect_ratio=campaign["aspect_ratio"],
            language="English",
            tone=campaign["tone"] or "clear, operational, credible",
            presenter_mode="none",
            real_ui_percent=85,
            generated_percent=15,
            budget_preference="Governed",
            quality_preference="High",
            production_constraints=[
                "Use only approved FleetPilot claims.",
                "Preserve approved FleetPilot UI exactly.",
            ],
        )
    def latest_director_plan(self, campaign_id: str) -> dict[str, Any] | None:
        rows = self.store.list("director_plans", {"campaign_id": campaign_id})
        if not rows:
            return None
        row = sorted(rows, key=lambda item: int(item["version"]))[-1]
        return self.director.get_plan(row["id"])

    def generate_director(self, campaign_id: str) -> dict[str, Any]:
        campaign = self.get_campaign(campaign_id)
        self.advance_stage(campaign_id, "DIRECTOR")
        plan = self.director.generate_plan(
            campaign_id, self._brief(campaign), self.brand(campaign_id)
        )
        return self.director.get_plan(plan["id"])

    def approve_director(self, campaign_id: str) -> dict[str, Any]:
        plan = self.latest_director_plan(campaign_id)
        if not plan:
            raise ValueError("director plan is required")
        if plan["status"] != "APPROVED":
            self.director.approve_plan(plan["id"])
        boards = self.store.list("storyboards", {"campaign_id": campaign_id})
        if boards:
            board = boards[0]
            scenes = self.store.list("scenes", {"storyboard_id": board["id"]})
        else:
            materialized = self.director.materialize_storyboard(
                plan["id"], "FleetPilot Meta Lead Campaign"
            )
            board = materialized["storyboard"]
            scenes = materialized["scenes"]
        self.advance_stage(campaign_id, "SCRIPT")
        return {
            "plan": self.director.get_plan(plan["id"]),
            "storyboard": board,
            "scenes": scenes,
        }

    def storyboard(self, campaign_id: str) -> dict[str, Any] | None:
        boards = self.store.list("storyboards", {"campaign_id": campaign_id})
        if not boards:
            return None
        board = boards[0]
        scenes = self.store.list("scenes", {"storyboard_id": board["id"]})
        campaign = self.get_campaign(campaign_id)
        return {
            "storyboard": board,
            "scenes": scenes,
            "duration_seconds": sum(int(s["duration_seconds"]) for s in scenes),
            "aspect_ratio": campaign["aspect_ratio"],
            "campaign_duration_seconds": int(campaign["duration_seconds"]),
        }
    def _ensure_static_requirement(
        self, campaign_id: str
    ) -> dict[str, Any]:
        board_data = self.storyboard(campaign_id)
        if not board_data:
            raise ValueError("approved storyboard is required")
        scenes = board_data["scenes"]
        scene = next(
            (
                item for item in scenes
                if not bool(item.get("immutable_ui"))
                and item.get("generation_method") != "COMPOSITING_ONLY"
            ),
            None,
        )
        if not scene:
            raise ValueError("no generative scene is available")
        existing = [
            row for row in self.store.list(
                "asset_requirements", {"scene_id": scene["id"]}
            )
            if row["purpose"] == CAMPAIGN_ASSET_PURPOSE
        ]
        if existing:
            return existing[0]
        campaign = self.get_campaign(campaign_id)
        generation = GenerationService(
            self.store, DeterministicMockGenerationProvider()
        )
        return generation.create_requirement(
            scene["id"],
            {
                "asset_type": "image",
                "purpose": CAMPAIGN_ASSET_PURPOSE,
                "description": (
                    "One governed FleetPilot Meta lead creative. "
                    "Provider submission requires explicit cost approval."
                ),
                "width": 1080,
                "height": 1080,
                "aspect_ratio": campaign["aspect_ratio"],
                "priority": "NORMAL",
                "status": "PENDING",
            },
        )

    def asset_plan(self, campaign_id: str) -> dict[str, Any]:
        requirement = self._ensure_static_requirement(campaign_id)
        board_data = self.storyboard(campaign_id)
        assert board_data is not None
        assets = self.store.list("assets", {"campaign_id": campaign_id})
        items: list[dict[str, Any]] = [
            {
                "kind": "GENERATED",
                "requirement_id": requirement["id"],
                "purpose": requirement["purpose"],
                "status": "NOT_GENERATED",
                "provider": "HIGGSFIELD",
                "model": "marketing-studio/image",
                "format": "image",
                "aspect_ratio": requirement["aspect_ratio"],
                "quantity": 1,
            }
        ]
        for scene in board_data["scenes"]:
            if not bool(scene.get("immutable_ui")):
                continue
            has_asset = any(asset.get("scene_id") == scene["id"] for asset in assets)
            items.append(
                {
                    "kind": "REAL_UI",
                    "scene_id": scene["id"],
                    "purpose": scene["title"],
                    "status": "EXISTING" if has_asset else "REQUIRED",
                    "provider": "COMPOSITING",
                    "model": None,
                    "format": "approved product UI",
                    "aspect_ratio": self.get_campaign(campaign_id)["aspect_ratio"],
                    "quantity": 1,
                }
            )
        self.advance_stage(campaign_id, "ASSET_PLAN")
        return {"campaign_id": campaign_id, "items": items, "quantity": len(items)}
    def _generation_prompt(self, campaign: dict[str, Any]) -> str:
        return (
            "Create one premium FleetPilot Meta campaign image for "
            + campaign["audience"]
            + ". Objective: "
            + campaign["objective"]
            + ". Offer: "
            + campaign["offer"]
            + ". CTA: "
            + (campaign["cta"] or "Book a FleetPilot demo")
            + ". Use only approved FleetPilot product claims. "
              "Do not invent metrics, customers, guarantees, awards, integrations, "
              "savings percentages, or customer results."
        )

    def ensure_generation_request(self, campaign_id: str) -> dict[str, Any]:
        campaign = self.get_campaign(campaign_id)
        requirement = self._ensure_static_requirement(campaign_id)
        policies = self.store.list(
            "generation_budget_policies",
            {"tenant_id": TENANT_ID, "campaign_id": campaign_id},
        )
        if not policies:
            BudgetGuard(self.store).set_policy(
                TENANT_ID,
                campaign_id,
                campaign_limit_minor=500,
                tenant_daily_limit_minor=1000,
                approval_required_minor=1,
                max_attempts=1,
            )
        request = self.orchestrator.create_request(
            asset_requirement_id=requirement["id"],
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            idempotency_key="saas:" + campaign_id + ":static-meta:v1",
            intent="STATIC_META",
            original_prompt=self._generation_prompt(campaign),
            business_claims=[
                "operational visibility",
                "trip profitability",
                "fleet control",
                "accountability",
            ],
        )
        if int(request["lifecycle_step"]) == 0:
            board_data = self.storyboard(campaign_id)
            scenes = board_data["scenes"] if board_data else []
            script = " | ".join(str(scene.get("script") or "") for scene in scenes)
            self.orchestrator.plan(
                request["id"],
                actor=USER_ID,
                duration_seconds=min(int(campaign["duration_seconds"]), 30),
                aspect_ratio=campaign["aspect_ratio"],
                script=script,
                storyboard=[
                    {
                        "scene_number": scene["position"],
                        "title": scene["title"],
                        "duration_seconds": scene["duration_seconds"],
                    }
                    for scene in scenes
                ],
            )
            request = self.store.get("generation_requests", request["id"])
        if int(request["lifecycle_step"]) == 1:
            self.orchestrator.cost(request["id"], actor=USER_ID)
            request = self.store.get("generation_requests", request["id"])
        if int(request["lifecycle_step"]) != 2:
            raise ValueError("generation request advanced beyond cost approval boundary")
        self.advance_stage(campaign_id, "COST_APPROVAL_REQUIRED")
        return self.generation_request(campaign_id)
    def generation_request(
        self, campaign_id: str
    ) -> dict[str, Any] | None:
        rows = self.store.list(
            "generation_requests",
            {"tenant_id": TENANT_ID, "campaign_id": campaign_id},
        )
        if not rows:
            return None
        request = sorted(rows, key=lambda row: row["created_at"])[-1]
        route = _decode(request.get("route_json"), {})
        ledger = self.store.list(
            "generation_spend_ledger", {"request_id": request["id"]}
        )
        attempts = self.store.list(
            "generation_attempts", {"request_id": request["id"]}
        )
        approvals = self.store.list(
            "generation_approvals", {"request_id": request["id"]}
        )
        results = self.store.list(
            "generation_results", {"request_id": request["id"]}
        )
        return {
            "id": request["id"],
            "campaign_id": campaign_id,
            "lifecycle_state": request["lifecycle_state"],
            "provider": route.get("provider"),
            "model": route.get("model"),
            "intent": request["intent"],
            "quantity": 1,
            "estimated_cost_minor": request["estimated_cost_minor"],
            "estimated_cost": _money(
                request["estimated_cost_minor"],
                request["currency_minor_exponent"],
                request["currency"],
            ),
            "currency": request["currency"],
            "currency_minor_exponent": request["currency_minor_exponent"],
            "approval_required": bool(request["approval_required"]),
            "approval_state": (
                "COST_APPROVAL_REQUIRED"
                if int(request["lifecycle_step"]) == 2
                else request["lifecycle_state"]
            ),
            "campaign_duration_seconds": int(
                self.get_campaign(campaign_id)["duration_seconds"]
            ),
            "aspect_ratio": self.get_campaign(campaign_id)["aspect_ratio"],
            "provider_submissions": len(
                [row for row in attempts if row.get("provider_request_id")]
            ),
            "generation_attempts": len(attempts),
            "budget_reservations": len(
                [row for row in ledger if row["event_type"] == "RESERVED"]
            ),
            "spend_events": len(ledger),
            "approval_records": len(approvals),
            "result_count": len(results),
            "actual_spend": "USD 0.00" if not results else None,
        }

    def governance(self, campaign_id: str) -> dict[str, Any]:
        request = self.generation_request(campaign_id)
        if not request:
            return {
                "automated_qa": "NOT_GENERATED",
                "provenance": "NOT_GENERATED",
                "human_review": "NOT_GENERATED",
                "export": "NOT_GENERATED",
                "publishing": "MANUAL_ONLY",
                "auto_publish": False,
            }
        rows = self.store.list(
            "generation_requests",
            {"tenant_id": TENANT_ID, "campaign_id": campaign_id},
        )
        raw = sorted(rows, key=lambda row: row["created_at"])[-1]
        qa = self.store.list("generation_gate_runs", {"request_id": raw["id"]})
        prov = self.store.list("generation_provenance", {"request_id": raw["id"]})
        exports = self.store.list("export_jobs", {"campaign_id": campaign_id})
        reviews = self.store.list(
            "generation_approvals",
            {"request_id": raw["id"], "approval_type": "HUMAN_REVIEW"},
        )
        return {
            "automated_qa": qa[0]["result"] if qa else "NOT_GENERATED",
            "provenance": "AVAILABLE" if prov else "NOT_GENERATED",
            "human_review": (
                reviews[0]["decision"] if reviews else "WAITING_FOR_QA"
            ),
            "export": exports[0]["state"] if exports else "NOT_AVAILABLE",
            "publishing": "MANUAL_ONLY",
            "auto_publish": False,
        }
