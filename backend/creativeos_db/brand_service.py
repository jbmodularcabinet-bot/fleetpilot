from __future__ import annotations

import json
from typing import Any

from .brand_brain import fleetpilot_fixture, validate_brand_payload
from .store import CreativeOSStore

BRAND_JSON_FIELDS = {
    "palette_json", "fonts_json", "messaging_json", "cta_rules_json",
    "prohibited_visuals_json", "approved_refs_json", "immutable_rules_json",
    "pain_points_json", "proof_points_json", "prohibited_messaging_json",
    "preferred_terms_json", "prohibited_terms_json", "campaign_languages_json",
    "approved_ui_folders_json", "protected_screens_json", "allowed_ui_transforms_json",
    "prohibited_generative_transforms_json", "visual_rules_json",
}

class BrandBrainService:
    def __init__(self, store: CreativeOSStore):
        self.store = store

    def _decode(self, row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        for key in BRAND_JSON_FIELDS:
            if key in result and isinstance(result[key], str):
                result[key] = json.loads(result[key])
        if "default_immutable_ui" in result:
            result["default_immutable_ui"] = bool(result["default_immutable_ui"])
        return result
    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        return self._decode(self.store.create("brand_profiles", validate_brand_payload(values)))

    def update(self, brand_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return self._decode(self.store.update("brand_profiles", brand_id, values))

    def get(self, brand_id: str) -> dict[str, Any]:
        return self._decode(self.store.get("brand_profiles", brand_id))

    def delete(self, brand_id: str) -> None:
        self.store.delete("brand_profiles", brand_id)

    def load_fleetpilot_fixture(self) -> dict[str, Any]:
        existing = self.store.list("brand_profiles", {"id": "brand-fleetpilot-golden"})
        if existing:
            return self._decode(existing[0])
        return self.create(fleetpilot_fixture())

    def add_memory(self, brand_id: str, decision_type: str, note: str, source: str = "local") -> dict[str, Any]:
        if decision_type not in {"accepted", "rejected", "note"}:
            raise ValueError("decision_type must be accepted, rejected, or note")
        if not note.strip():
            raise ValueError("creative memory note is required")
        return self.store.create("creative_memory", {
            "brand_profile_id": brand_id,
            "decision_type": decision_type,
            "note": note.strip(),
            "source": source,
        })
