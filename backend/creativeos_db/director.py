from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

ALLOWED_FORMATS = {"60s Explainer", "30s Ad", "15s Reel", "Product Walkthrough", "Landing Hero"}
ALLOWED_RATIOS = {"16:9", "9:16", "1:1"}
SCENE_TYPES = {"REAL_UI", "AI_VIDEO", "AI_IMAGE", "TYPOGRAPHY", "PRESENTER"}

@dataclass(frozen=True)
class CampaignBrief:
    brand_profile_id: str
    objective: str
    target_audience: str
    awareness_level: str
    pain_points: list[str]
    core_offer: str
    cta: str
    campaign_format: str
    duration_seconds: int
    aspect_ratio: str
    language: str
    tone: str
    presenter_mode: str
    real_ui_percent: int
    generated_percent: int
    budget_preference: str
    quality_preference: str
    production_constraints: list[str]


def validate_brief(brief: CampaignBrief) -> None:
    if not brief.objective.strip(): raise ValueError("campaign objective is required")
    if not brief.target_audience.strip(): raise ValueError("target audience is required")
    if brief.campaign_format not in ALLOWED_FORMATS: raise ValueError("unsupported campaign format")
    if brief.aspect_ratio not in ALLOWED_RATIOS: raise ValueError("unsupported aspect ratio")
    if brief.duration_seconds <= 0 or brief.duration_seconds > 600: raise ValueError("duration must be between 1 and 600 seconds")
    if not 0 <= brief.real_ui_percent <= 100 or not 0 <= brief.generated_percent <= 100:
        raise ValueError("production percentages must be between 0 and 100")
    if brief.real_ui_percent + brief.generated_percent > 100:
        raise ValueError("real UI and generated percentages cannot exceed 100")


def validate_output(plan: dict[str, Any]) -> None:
    required = {"strategy", "hooks", "message_hierarchy", "script", "visual_plan", "asset_needs", "provider_recommendations", "cost_estimate", "scene_plan"}
    missing = required - set(plan)
    if missing: raise ValueError(f"director output missing: {sorted(missing)}")
    if len(plan["hooks"]) < 3: raise ValueError("director output requires a primary and two alternate hooks")
    if not plan["scene_plan"]: raise ValueError("director output requires at least one scene")
    for scene in plan["scene_plan"]:
        if scene.get("scene_type") not in SCENE_TYPES: raise ValueError("invalid scene type")
        if int(scene.get("duration_seconds", 0)) <= 0: raise ValueError("scene duration must be positive")

class CreativeDirectorProvider(Protocol):
    mode: str
    def generate(self, brief: CampaignBrief, brand: dict[str, Any]) -> dict[str, Any]: ...

class DeterministicMockCreativeDirectorProvider:
    mode = "MOCK"

    def generate(self, brief: CampaignBrief, brand: dict[str, Any]) -> dict[str, Any]:
        validate_brief(brief)
        protected = bool(brand.get("default_immutable_ui", False))
        if brand.get("name") == "FleetPilot":
            titles = ["Hook", "Command Center", "Live Fleet", "Dispatch", "Accountability", "Profitability", "Intelligence", "Close"]
            durations = [5, 8, 7, 8, 7, 8, 8, 7]
        else:
            titles = ["Hook", "Problem", "Product", "Proof", "Close"]
            base = max(3, brief.duration_seconds // len(titles))
            durations = [base] * len(titles)
        scenes = []
        for i, title in enumerate(titles):
            is_ui = protected and i not in {0, len(titles)-1}
            scene_type = "REAL_UI" if is_ui else ("TYPOGRAPHY" if i == len(titles)-1 else "AI_VIDEO")
            method = "COMPOSITING_ONLY" if is_ui else "GENERATIVE"
            scenes.append({"scene_number": i+1, "title": title, "narrative_purpose": f"Advance the campaign through {title.lower()}.", "duration_seconds": durations[i], "scene_type": scene_type, "script": f"{title}: {brief.core_offer or brand.get('core_promise','')}", "visual_direction": "Preserve approved interface exactly; use crop, pan, focus and callouts only." if is_ui else "Use restrained cinematic support visuals consistent with the brand.", "asset_requirements": ["approved product UI"] if is_ui else ["support visual"], "recommended_generation_method": method})
        return self._build_output(brief, brand, scenes)

    def _build_output(self, brief: CampaignBrief, brand: dict[str, Any], scenes: list[dict[str, Any]]) -> dict[str, Any]:
        promise = brand.get("core_promise") or brief.core_offer
        hook = "Profit leaks start where visibility ends." if brand.get("name") == "FleetPilot" else f"See what changes when {promise.lower()}."
        script = [{"scene_number": s["scene_number"], "voiceover": s["script"], "on_screen_copy": s["title"], "timing_seconds": s["duration_seconds"]} for s in scenes]
        low, high = estimate_cost(scenes)
        plan = {
            "strategy": {"campaign_angle": "Product truth first", "audience_tension": brief.pain_points[0] if brief.pain_points else "Fragmented workflow", "central_promise": promise, "proof_structure": ["problem", "product", "proof", "CTA"], "cta_strategy": brief.cta, "emotional_tone": brief.tone, "pacing": "clear and controlled"},
            "hooks": [hook, f"{brand.get('tagline','A clearer way to work.')}", "Turn scattered operations into one visible system."],
            "message_hierarchy": {"primary": promise, "supporting": brand.get("messaging_json", []), "proof_points": brand.get("proof_points_json", [])},
            "script": script,
            "visual_plan": [{"scene_number": s["scene_number"], "purpose": s["narrative_purpose"], "scene_type": s["scene_type"], "camera_motion": "restrained", "transition_family": "editorial", "motion_intensity": "low" if s["scene_type"] == "REAL_UI" else "medium"} for s in scenes],
            "asset_needs": {"screenshots": ["approved SaaS UI"] if brief.real_ui_percent else [], "logos": ["primary logo"], "presenter_references": [], "voice_assets": ["voiceover"], "missing_assets": []},
            "provider_recommendations": {"strategy": "LLM", "real_ui": "COMPOSITING", "support_video": "VIDEO_MODEL", "voice": "VOICE_MODEL"},
            "cost_estimate": {"label": "ESTIMATE", "low_cents": low, "high_cents": high, "scene_estimates": [scene_cost(s) for s in scenes]},
            "scene_plan": scenes,
        }
        validate_output(plan)
        return plan

class LiveLLMCreativeDirectorProvider:
    mode = "LIVE"
    def __init__(self, configured: bool = False):
        self.configured = configured
    def generate(self, brief: CampaignBrief, brand: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("live Creative Director provider is not configured")
        raise NotImplementedError("live provider adapter contract exists; implementation requires configured credentials")


def scene_cost(scene: dict[str, Any]) -> dict[str, Any]:
    method = scene.get("recommended_generation_method")
    scene_type = scene.get("scene_type")
    if method == "COMPOSITING_ONLY": low, high = 0, 0
    elif scene_type == "AI_IMAGE": low, high = 20, 60
    elif scene_type == "PRESENTER": low, high = 120, 350
    elif scene_type == "AI_VIDEO": low, high = 80, 250
    else: low, high = 10, 40
    return {"scene_number": scene.get("scene_number"), "low_cents": low, "high_cents": high}


def estimate_cost(scenes: list[dict[str, Any]]) -> tuple[int, int]:
    costs = [scene_cost(s) for s in scenes]
    return sum(c["low_cents"] for c in costs), sum(c["high_cents"] for c in costs)


def brief_to_dict(brief: CampaignBrief) -> dict[str, Any]:
    return asdict(brief)
