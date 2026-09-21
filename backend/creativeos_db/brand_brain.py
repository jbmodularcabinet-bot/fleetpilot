from __future__ import annotations

import json
import re
from pathlib import PureWindowsPath
from typing import Any

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
ALLOWED_RULE_KEYS = {"must_preserve", "may_adapt", "never_do"}


def _json_list(value: Any, field: str) -> list[Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} must contain valid JSON") from exc
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def validate_local_path(value: str | None) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str) or not PureWindowsPath(value).is_absolute():
        raise ValueError(f"asset path must be an absolute Windows path: {value!r}")


def validate_brand_payload(values: dict[str, Any]) -> dict[str, Any]:
    data = dict(values)
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("brand name is required")
    data["name"] = name

    palette = _json_list(data.get("palette_json", []), "palette_json")
    if any(not isinstance(c, str) or not HEX_COLOR.match(c) for c in palette):
        raise ValueError("palette_json must be a list of #RRGGBB colors")
    data["palette_json"] = palette

    fonts = _json_list(data.get("fonts_json", []), "fonts_json")
    if any(not isinstance(f, str) or not f.strip() for f in fonts):
        raise ValueError("fonts_json must be a list of font names")
    data["fonts_json"] = fonts

    for key in ("logo_path", "icon_path"):
        validate_local_path(data.get(key))
    folders = _json_list(data.get("approved_ui_folders_json", []), "approved_ui_folders_json")
    for path in folders:
        validate_local_path(path)
    data["approved_ui_folders_json"] = folders
    rules = data.get("immutable_rules_json", {}) or {}
    if isinstance(rules, str):
        try:
            rules = json.loads(rules)
        except json.JSONDecodeError as exc:
            raise ValueError("immutable_rules_json must contain valid JSON") from exc
    if not isinstance(rules, dict) or any(k not in ALLOWED_RULE_KEYS for k in rules):
        raise ValueError("immutable rules must use must_preserve, may_adapt, never_do")
    for key, value in rules.items():
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"immutable rule {key} must be a list of strings")
    data["immutable_rules_json"] = rules
    data["default_immutable_ui"] = bool(data.get("default_immutable_ui", False))
    return data


def fleetpilot_fixture() -> dict[str, Any]:
    return {
        "id": "brand-fleetpilot-golden",
        "name": "FleetPilot",
        "display_name": "FleetPilot",
        "description": "Fleet management SaaS and logistics operating system.",
        "industry": "Fleet Management SaaS / Logistics Operating System",
        "palette_json": ["#0F1514", "#56E0B0", "#F5F7F6"],
        "fonts_json": ["Inter"],
        "positioning": "One operating system for fleet visibility, dispatch control, accountability, and profitability.",
        "audience": "Philippine trucking company owners, managers, dispatchers, operators",
        "core_promise": "Improved fleet visibility, dispatch control, trip accountability, and profitability.",
        "tagline": "Track. Dispatch. Control. Grow.",
        "messaging_json": ["operational visibility", "trip profitability", "fleet control", "accountability"],
        "default_immutable_ui": True,
        "immutable_rules_json": {
            "must_preserve": ["Approved FleetPilot UI screenshots and screen recordings"],
            "may_adapt": ["Crop", "Scale", "Pan", "Zoom", "Callouts", "Cursor motion"],
            "never_do": ["Generative repainting", "Text recreation", "Layout regeneration"],
        },
        "approved_ui_folders_json": [],
        "approved_refs_json": [],
        "cta_rules_json": ["Use only approved product claims and direct product CTAs"],
        "prohibited_visuals_json": ["Distorted or regenerated FleetPilot interface"],
    }
