from __future__ import annotations

import json
from typing import Any

from .brand_service import BrandBrainService
from .director import CampaignBrief, CreativeDirectorProvider, brief_to_dict, validate_output
from .store import CreativeOSStore, now_iso


class CreativeDirectorService:
    def __init__(self, store: CreativeOSStore, provider: CreativeDirectorProvider):
        self.store = store
        self.provider = provider

    def generate_plan(self, campaign_id: str, brief: CampaignBrief, brand: dict[str, Any]) -> dict[str, Any]:
        campaign = self.store.get("campaigns", campaign_id)
        expected_brand_id = campaign["brand_profile_id"]
        if brief.brand_profile_id != expected_brand_id:
            raise ValueError("campaign and brief Brand Brain do not match")
        if brand.get("id") not in {None, expected_brand_id}:
            raise ValueError("campaign resolved a different Brand Brain")
        # Keep the legacy argument for callers, but never trust supplied brand content.
        brand = BrandBrainService(self.store).get(expected_brand_id)
        output = self.provider.generate(brief, brand)
        validate_output(output)
        existing = self.store.list("director_plans", {"campaign_id": campaign_id})
        version = max([int(row["version"]) for row in existing], default=0) + 1
        return self.store.create("director_plans", {
            "campaign_id": campaign_id,
            "version": version,
            "provider_mode": self.provider.mode,
            "status": "DRAFT",
            "brief_json": brief_to_dict(brief),
            "output_json": output,
        })

    def generate_plan_for_campaign(
        self, campaign_id: str, brief: CampaignBrief
    ) -> dict[str, Any]:
        campaign = self.store.get("campaigns", campaign_id)
        brand = BrandBrainService(self.store).get(campaign["brand_profile_id"])
        return self.generate_plan(campaign_id, brief, brand)

    def approve_plan(self, plan_id: str) -> dict[str, Any]:
        plan = self.store.get("director_plans", plan_id)
        return self.store.update("director_plans", plan_id, {
            "status": "APPROVED",
            "approved_at": now_iso(),
        })

    def materialize_storyboard(self, plan_id: str, title: str = "Director Storyboard") -> dict[str, Any]:
        plan = self.store.get("director_plans", plan_id)
        if plan["status"] != "APPROVED":
            raise ValueError("director plan must be approved before storyboard materialization")
        output = json.loads(plan["output_json"]) if isinstance(plan["output_json"], str) else plan["output_json"]
        board = self.store.create("storyboards", {"campaign_id": plan["campaign_id"], "title": title, "status": "READY"})
        created = []
        for scene in output["scene_plan"]:
            created.append(self.store.create("scenes", {
                "storyboard_id": board["id"], "position": scene["scene_number"], "title": scene["title"],
                "purpose": scene["narrative_purpose"], "duration_seconds": scene["duration_seconds"],
                "script": scene["script"], "visual_direction": scene["visual_direction"],
                "scene_type": scene["scene_type"], "status": "READY", "approval_state": "DRAFT",
                "asset_requirements_json": scene.get("asset_requirements", []),
                "generation_method": scene.get("recommended_generation_method","GENERATIVE"),
                "immutable_ui": scene.get("scene_type")=="REAL_UI",
                "provider_recommendation": "COMPOSITING" if scene.get("scene_type")=="REAL_UI" else "AUTO",
            }))
        return {"storyboard": board, "scenes": created}

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        row = self.store.get("director_plans", plan_id)
        for key in ("brief_json", "output_json"):
            if isinstance(row[key], str): row[key] = json.loads(row[key])
        return row
