from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .router import ProviderRouter
from .store import CreativeOSStore

BUDGET_STATES = {"WITHIN_BUDGET", "NEAR_LIMIT", "OVER_BUDGET", "UNKNOWN"}
ISO_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _currency(value: str) -> str:
    code = str(value or "").upper().strip()
    if not ISO_CURRENCY.fullmatch(code):
        raise ValueError("currency must be an ISO 4217 three-letter code")
    return code


def _minor(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be integer minor units or null")
    if value < 0:
        raise ValueError(f"{field} cannot be negative")
    return value


def _json(value: str | None) -> Any:
    return json.loads(value) if value else None


class CostOptimizer:
    def __init__(self, store: CreativeOSStore, router: ProviderRouter):
        self.store = store
        self.router = router
    def create_profile(self, values: dict[str, Any]) -> dict[str, Any]:
        data = dict(values)
        data["provider"] = str(data.get("provider", "")).upper().strip()
        data["model"] = str(data.get("model", "")).strip()
        data["capability"] = str(data.get("capability", "")).lower().strip()
        registration = self.router.registration(data["provider"])
        if data["capability"] not in registration.capabilities:
            raise ValueError("provider does not support cost-profile capability")
        data["quality_tier"] = str(data.get("quality_tier", "")).upper().strip()
        data["currency"] = _currency(str(data.get("currency", "")))
        if not data["provider"] or not data["model"] or not data["quality_tier"]:
            raise ValueError("provider, model, and quality_tier are required")
        exponent = int(data.get("currency_minor_exponent", -1))
        if exponent < 0 or exponent > 6:
            raise ValueError("currency_minor_exponent must be between 0 and 6")
        data["currency_minor_exponent"] = exponent
        for field in ("fixed_cost_minor", "per_image_cost_minor", "per_second_cost_minor", "per_unit_cost_minor"):
            data[field] = _minor(data.get(field), field)
        if int(data.get("version", 0)) <= 0:
            raise ValueError("version must be positive")
        if not str(data.get("effective_at", "")).strip():
            raise ValueError("effective_at is required")
        return self.store.create("provider_cost_profiles", data)

    def create_fx_snapshot(self, values: dict[str, Any]) -> dict[str, Any]:
        data = dict(values)
        data["from_currency"] = _currency(str(data.get("from_currency", "")))
        data["to_currency"] = _currency(str(data.get("to_currency", "")))
        for field in ("from_minor_exponent", "to_minor_exponent"):
            exponent = int(data.get(field, -1))
            if exponent < 0 or exponent > 6:
                raise ValueError(f"{field} must be between 0 and 6")
            data[field] = exponent
        try:
            rate = Decimal(str(data.get("rate_decimal", "")))
        except InvalidOperation as exc:
            raise ValueError("invalid FX rate") from exc
        if rate <= 0:
            raise ValueError("FX rate must be positive")
        data["rate_decimal"] = format(rate, "f")
        for field in ("rate_source", "rate_effective_at", "captured_at"):
            if not str(data.get(field, "")).strip():
                raise ValueError(f"{field} is required")
        return self.store.create("fx_snapshots", data)

    def set_campaign_budget(self, campaign_id: str, total_minor: int | None,
                            currency: str | None, minor_exponent: int | None,
                            near_limit_bps: int = 9000) -> dict[str, Any]:
        self.store.get("campaigns", campaign_id)
        if total_minor is not None:
            total_minor = _minor(total_minor, "total_minor")
            if currency is None or minor_exponent is None:
                raise ValueError("budget currency and minor exponent are required")
            code = _currency(currency)
            exponent = int(minor_exponent)
            if exponent < 0 or exponent > 6:
                raise ValueError("budget minor exponent must be between 0 and 6")
        else:
            code, exponent = None, None
        if not 1 <= int(near_limit_bps) <= 10000:
            raise ValueError("near_limit_bps must be between 1 and 10000")
        return self.store.update("campaigns", campaign_id, {
            "budget_cents": total_minor,
            "budget_currency": code,
            "budget_minor_exponent": exponent,
            "near_limit_bps": int(near_limit_bps),
        })

    def _campaign_for_requirement(self, requirement_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        req = self.store.get("asset_requirements", requirement_id)
        scene = self.store.get("scenes", req["scene_id"])
        board = self.store.get("storyboards", scene["storyboard_id"])
        campaign = self.store.get("campaigns", board["campaign_id"])
        return req, scene, campaign

    def _original_cost(self, profile: dict[str, Any], requirement: dict[str, Any],
                       image_count: int = 1, unit_count: int | None = None) -> tuple[int | None, dict[str, Any]]:
        fixed = profile["fixed_cost_minor"]
        per_image = profile["per_image_cost_minor"]
        per_second = profile["per_second_cost_minor"]
        per_unit = profile["per_unit_cost_minor"]
        if all(v is None for v in (fixed, per_image, per_second, per_unit)):
            return None, {"reason": "NO_PRICING"}
        total = int(fixed or 0)
        components: dict[str, Any] = {"fixed_cost_minor": fixed}
        if per_image is not None:
            if image_count < 0:
                raise ValueError("image_count cannot be negative")
            total += int(per_image) * image_count
            components["image_count"] = image_count
            components["per_image_cost_minor"] = per_image
        if per_second is not None:
            duration = requirement.get("duration_seconds")
            if duration is None:
                return None, {"reason": "MISSING_DURATION"}
            duration = int(duration)
            if duration < 0:
                raise ValueError("duration cannot be negative")
            total += int(per_second) * duration
            components["duration_seconds"] = duration
            components["per_second_cost_minor"] = per_second
        if per_unit is not None:
            if unit_count is None:
                return None, {"reason": "MISSING_UNIT_COUNT"}
            if unit_count < 0:
                raise ValueError("unit_count cannot be negative")
            total += int(per_unit) * unit_count
            components["unit_count"] = unit_count
            components["per_unit_cost_minor"] = per_unit
        components["total_original_minor"] = total
        return total, components

    def _normalize(self, amount_minor: int | None, profile: dict[str, Any], campaign: dict[str, Any],
                   fx_snapshot: dict[str, Any] | None) -> tuple[int | None, dict[str, Any] | None]:
        if amount_minor is None:
            return None, None
        budget_currency = campaign.get("budget_currency")
        budget_exp = campaign.get("budget_minor_exponent")
        if not budget_currency or budget_exp is None:
            return None, None
        if profile["currency"] == budget_currency:
            if int(profile["currency_minor_exponent"]) != int(budget_exp):
                return None, None
            return amount_minor, None
        if fx_snapshot is None:
            return None, None
        if (fx_snapshot["from_currency"] != profile["currency"] or
                fx_snapshot["to_currency"] != budget_currency or
                int(fx_snapshot["from_minor_exponent"]) != int(profile["currency_minor_exponent"]) or
                int(fx_snapshot["to_minor_exponent"]) != int(budget_exp)):
            raise ValueError("FX snapshot does not match route currencies/exponents")
        rate = Decimal(str(fx_snapshot["rate_decimal"]))
        source_scale = Decimal(10) ** int(profile["currency_minor_exponent"])
        target_scale = Decimal(10) ** int(budget_exp)
        major = Decimal(amount_minor) / source_scale
        converted = (major * rate * target_scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(converted), dict(fx_snapshot)

    def _budget_state(self, campaign: dict[str, Any], committed: int, planned: int,
                      candidate: int | None) -> tuple[str, int | None]:
        budget = campaign.get("budget_cents")
        if budget is None or not campaign.get("budget_currency") or candidate is None:
            return "UNKNOWN", None
        projected = int(committed) + int(planned) + int(candidate)
        budget = int(budget)
        if projected > budget:
            return "OVER_BUDGET", projected
        bps = int(campaign.get("near_limit_bps") or 9000)
        if projected * 10000 >= budget * bps:
            return "NEAR_LIMIT", projected
        return "WITHIN_BUDGET", projected

    def recommend(self, requirement_id: str, required_quality: str,
                  committed_cost_minor: int = 0, planned_cost_minor: int = 0,
                  fx_snapshot_ids: dict[tuple[str, str], str] | None = None,
                  image_count: int = 1, unit_count: int | None = None) -> dict[str, Any]:
        committed_cost_minor = _minor(committed_cost_minor, "committed_cost_minor") or 0
        planned_cost_minor = _minor(planned_cost_minor, "planned_cost_minor") or 0
        req, scene, campaign = self._campaign_for_requirement(requirement_id)
        capability = str(req["asset_type"]).lower()
        quality = str(required_quality).upper().strip()
        if not quality:
            raise ValueError("required_quality is required")
        recommendation = self.store.create("cost_recommendations", {
            "asset_requirement_id": requirement_id, "campaign_id": campaign["id"],
            "budget_total_minor": campaign.get("budget_cents"),
            "budget_currency": campaign.get("budget_currency"),
            "budget_minor_exponent": campaign.get("budget_minor_exponent"),
            "committed_cost_minor": committed_cost_minor, "planned_cost_minor": planned_cost_minor,
            "near_limit_bps": int(campaign.get("near_limit_bps") or 9000),
        })
        profiles = [p for p in self.store.list("provider_cost_profiles")
                    if p["capability"] == capability and p["quality_tier"] == quality]
        created: list[dict[str, Any]] = []
        for profile in profiles:
            try:
                self.router.resolve(capability, profile["provider"], bool(scene.get("immutable_ui")))
            except (RuntimeError, ValueError):
                continue
            original, calc = self._original_cost(profile, req, image_count=image_count, unit_count=unit_count)
            fx = None
            if profile["currency"] != campaign.get("budget_currency") and fx_snapshot_ids:
                fx_id = fx_snapshot_ids.get((profile["currency"], campaign.get("budget_currency")))
                if fx_id:
                    fx = self.store.get("fx_snapshots", fx_id)
            normalized, fx_used = self._normalize(original, profile, campaign, fx)
            state, projected = self._budget_state(campaign, committed_cost_minor, planned_cost_minor, normalized)
            budget_snapshot = {
                "total_minor": campaign.get("budget_cents"), "currency": campaign.get("budget_currency"),
                "minor_exponent": campaign.get("budget_minor_exponent"),
                "committed_minor": committed_cost_minor, "planned_minor": planned_cost_minor,
                "near_limit_bps": int(campaign.get("near_limit_bps") or 9000),
                "projected_total_minor": projected,
            }
            estimate = self.store.create("cost_estimates", {
                "recommendation_id": recommendation["id"], "provider_cost_profile_id": profile["id"],
                "fx_snapshot_id": fx["id"] if fx_used else None,
                "provider": profile["provider"], "model": profile["model"],
                "capability": capability, "quality_tier": quality,
                "original_cost_minor": original, "original_currency": profile["currency"],
                "normalized_cost_minor": normalized,
                "normalized_currency": campaign.get("budget_currency") if normalized is not None else None,
                "budget_state": state, "is_recommended": 0,
                "profile_snapshot_json": dict(profile), "fx_snapshot_json": fx_used,
                "budget_snapshot_json": budget_snapshot, "calculation_json": calc,
            })
            created.append(estimate)
        eligible = [e for e in created if e["budget_state"] in {"WITHIN_BUDGET", "NEAR_LIMIT"}
                    and e["normalized_cost_minor"] is not None]
        if eligible:
            winner = sorted(eligible, key=lambda e: (int(e["normalized_cost_minor"]), e["provider"], e["model"], e["id"]))[0]
            self.store.conn.execute("UPDATE cost_estimates SET is_recommended=1 WHERE id=?", (winner["id"],))
            self.store.conn.commit()
            created = [self.store.get("cost_estimates", e["id"]) for e in created]
        return {"recommendation": recommendation, "estimates": created}
    def record_override(self, recommendation_id: str, selected_estimate_id: str,
                        reason: str) -> dict[str, Any]:
        reason = str(reason).strip()
        if not reason:
            raise ValueError("override reason is required")
        recommendation = self.store.get("cost_recommendations", recommendation_id)
        estimate = self.store.get("cost_estimates", selected_estimate_id)
        if estimate["recommendation_id"] != recommendation_id:
            raise ValueError("estimate does not belong to recommendation")
        req, scene, _campaign = self._campaign_for_requirement(recommendation["asset_requirement_id"])
        self.router.resolve(estimate["capability"], estimate["provider"], bool(scene.get("immutable_ui")))
        estimates = self.store.list("cost_estimates", {"recommendation_id": recommendation_id})
        original = next((e for e in estimates if e["is_recommended"]), None)
        evidence = {
            "original_recommended_estimate_id": original["id"] if original else None,
            "original_budget_state": original["budget_state"] if original else None,
            "selected_provider": estimate["provider"], "selected_model": estimate["model"],
            "selected_budget_state": estimate["budget_state"],
            "original_cost_minor": estimate["original_cost_minor"],
            "original_currency": estimate["original_currency"],
            "normalized_cost_minor": estimate["normalized_cost_minor"],
            "normalized_currency": estimate["normalized_currency"],
            "fx_snapshot": _json(estimate["fx_snapshot_json"]),
            "budget_snapshot": _json(estimate["budget_snapshot_json"]),
        }
        return self.store.create("cost_overrides", {
            "recommendation_id": recommendation_id,
            "selected_estimate_id": selected_estimate_id,
            "original_recommended_estimate_id": original["id"] if original else None,
            "reason": reason, "evidence_json": evidence,
        })

    def recommendation_snapshot(self, recommendation_id: str) -> dict[str, Any]:
        rec = self.store.get("cost_recommendations", recommendation_id)
        estimates = self.store.list("cost_estimates", {"recommendation_id": recommendation_id})
        overrides = self.store.list("cost_overrides", {"recommendation_id": recommendation_id})
        return {"recommendation": rec, "estimates": estimates, "overrides": overrides}
