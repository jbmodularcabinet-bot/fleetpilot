from __future__ import annotations
from typing import Any

SCENE_TYPES = {"REAL_UI","AI_VIDEO","AI_IMAGE","PRESENTER","TYPOGRAPHY","VOICE"}
SCENE_STATUSES = {"DRAFT","READY","GENERATING","REVIEW","APPROVED","FAILED"}
APPROVAL_STATES = {"DRAFT","APPROVED"}
GEN_METHODS = {"COMPOSITING_ONLY","GENERATIVE","PRESENTER","VOICE"}

def validate_scene(values: dict[str, Any]) -> None:
    title = str(values.get("title","")).strip()
    if not title: raise ValueError("scene title is required")
    if int(values.get("duration_seconds",0)) <= 0: raise ValueError("scene duration must be positive")
    if int(values.get("position",0)) <= 0: raise ValueError("scene position must be positive")
    if values.get("scene_type","REAL_UI") not in SCENE_TYPES: raise ValueError("invalid scene type")
    if values.get("status","DRAFT") not in SCENE_STATUSES: raise ValueError("invalid scene status")
    if values.get("approval_state","DRAFT") not in APPROVAL_STATES: raise ValueError("invalid approval state")
    if values.get("scene_type") == "REAL_UI" and values.get("immutable_ui", False):
        if values.get("generation_method","COMPOSITING_ONLY") != "COMPOSITING_ONLY":
            raise ValueError("immutable REAL_UI scenes must use COMPOSITING_ONLY")

def rollup(scenes: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "duration_seconds": sum(int(s.get("duration_seconds",0)) for s in scenes),
        "estimated_low_cents": sum(int(s.get("cost_estimate_low_cents",0)) for s in scenes),
        "estimated_high_cents": sum(int(s.get("cost_estimate_high_cents",0)) for s in scenes),
        "ready_count": sum(s.get("status") == "READY" for s in scenes),
        "approved_count": sum(s.get("approval_state") == "APPROVED" for s in scenes),
        "failed_count": sum(s.get("status") == "FAILED" for s in scenes),
    }

def next_version_number(versions: list[dict[str, Any]]) -> int:
    return max((int(v["version_number"]) for v in versions), default=0) + 1
