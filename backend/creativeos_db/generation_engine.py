from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .brand_service import BrandBrainService
from .higgsfield_provider import (
    HiggsfieldProvider,
    HiggsfieldProviderError,
    HiggsfieldSubmission,
)
from .queue import GenerationQueueService
from .store import CreativeOSStore, now_iso


LIFECYCLE = (
    "DRAFT",
    "PLANNED",
    "COSTED",
    "APPROVED",
    "QUEUED",
    "GENERATING",
    "GENERATED",
    "QA",
    "HUMAN_REVIEW",
    "APPROVED",
    "READY_FOR_EXPORT",
)
PRICE_SNAPSHOT = "HIGGSFIELD_PUBLIC_LIST_2026-09-27"
USD_EXPONENT = 4


def _decode(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _safe_component(value: str) -> str:
    keep = "".join(ch for ch in str(value) if ch.isalnum() or ch in "-_")
    return keep[:100] or "output"


@dataclass(frozen=True)
class RouteDecision:
    provider: str
    model: str
    capability: str
    intent: str
    settings: dict[str, Any]
    estimated_cost_minor: int
    currency: str = "USD"
    currency_minor_exponent: int = USD_EXPONENT
    premium: bool = False
    cost_source: str = PRICE_SNAPSHOT

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


class GenerationModelRouter:
    """Provider-neutral business intent -> provider route policy."""

    def route(
        self,
        intent: str,
        *,
        duration_seconds: int | None = None,
        aspect_ratio: str = "9:16",
        has_references: bool = False,
        explicit_premium_tier: bool = False,
    ) -> RouteDecision:
        intent = str(intent or "").upper().strip()
        duration = int(duration_seconds or 5)
        if duration <= 0 or duration > 30:
            raise ValueError("generation duration must be between 1 and 30 seconds")
        if intent == "STATIC_META":
            return RouteDecision(
                provider="HIGGSFIELD",
                model="marketing-studio/image",
                capability="image",
                intent=intent,
                settings={
                    "quality": "low",
                    "moderation": "auto",
                    "resolution": "1k",
                    "aspect_ratio": aspect_ratio,
                    "enhance_prompt": False,
                },
                estimated_cost_minor=190,
            )
        if intent == "VIDEO_EXPLORATION":
            return RouteDecision(
                provider="HIGGSFIELD",
                model="alibaba/wan-3.0-prime/text-to-video",
                capability="video",
                intent=intent,
                settings={
                    "duration": duration,
                    "resolution": "720p",
                    "aspect_ratio": aspect_ratio,
                    "generate_audio": True,
                    "enable_thinking": False,
                },
                estimated_cost_minor=680 * duration,
            )
        if intent == "PREMIUM_FINAL":
            model = (
                "bytedance/seedance-2.5/reference-to-video"
                if has_references
                else "bytedance/seedance-2.5/text-to-video"
            )
            return RouteDecision(
                provider="HIGGSFIELD",
                model=model,
                capability="video",
                intent=intent,
                settings={
                    "duration": duration,
                    "resolution": "720p",
                    "aspect_ratio": aspect_ratio,
                    "output_format": "mp4",
                    "generate_audio": True,
                },
                estimated_cost_minor=(1728 if has_references else 1440) * duration,
                premium=True,
            )
        if intent == "MOTION_TRANSFER":
            if not has_references:
                raise ValueError("motion transfer requires reference media")
            return RouteDecision(
                provider="HIGGSFIELD",
                model="higgsfield/genjutsu/motion-transfer/v1.0",
                capability="video",
                intent=intent,
                settings={
                    "resolution": "720p",
                    "duration": duration,
                },
                estimated_cost_minor=6810 * duration,
            )
        if intent == "PREMIUM_CINEMATIC":
            if not explicit_premium_tier:
                raise PermissionError(
                    "Cinema Studio is reserved behind explicit premium tier approval"
                )
            return RouteDecision(
                provider="HIGGSFIELD",
                model="higgsfield/cinema-studio/4.0",
                capability="video",
                intent=intent,
                settings={
                    "duration": duration,
                    "resolution": "720p",
                    "aspect_ratio": aspect_ratio,
                    "generate_audio": True,
                },
                estimated_cost_minor=4623 * duration,
                premium=True,
            )
        raise ValueError(f"unsupported generation intent: {intent}")

    @staticmethod
    def provider_input(
        route: RouteDecision,
        compiled_prompt: str,
        references: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {"prompt": compiled_prompt, **route.settings}
        image_urls = [
            str(item["url"])
            for item in references
            if item.get("type") == "image" and item.get("url")
        ]
        video_urls = [
            str(item["url"])
            for item in references
            if item.get("type") == "video" and item.get("url")
        ]
        audio_urls = [
            str(item["url"])
            for item in references
            if item.get("type") == "audio" and item.get("url")
        ]
        if route.model.endswith("/reference-to-video"):
            if image_urls:
                payload["image_urls"] = image_urls
            if video_urls:
                payload["video_urls"] = video_urls
            if audio_urls:
                payload["audio_urls"] = audio_urls
        elif route.model == "higgsfield/genjutsu/motion-transfer/v1.0":
            if not video_urls or not image_urls:
                raise ValueError(
                    "Genjutsu motion transfer needs a driving video and reference image"
                )
            payload["video_url"] = video_urls[0]
            payload["image_urls"] = image_urls
        elif route.model == "marketing-studio/image" and image_urls:
            payload["image_urls"] = image_urls
        return payload


class BudgetGuard:
    def __init__(self, store: CreativeOSStore):
        self.store = store

    def set_policy(
        self,
        tenant_id: str,
        campaign_id: str,
        *,
        campaign_limit_minor: int,
        tenant_daily_limit_minor: int,
        approval_required_minor: int,
        currency: str = "USD",
        currency_minor_exponent: int = USD_EXPONENT,
        max_attempts: int = 2,
        hard_cap: bool = True,
    ) -> dict[str, Any]:
        self.store.get("campaigns", campaign_id)
        values = {
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "campaign_limit_minor": int(campaign_limit_minor),
            "tenant_daily_limit_minor": int(tenant_daily_limit_minor),
            "approval_required_minor": int(approval_required_minor),
            "currency": str(currency).upper(),
            "currency_minor_exponent": int(currency_minor_exponent),
            "max_attempts": int(max_attempts),
            "hard_cap": int(bool(hard_cap)),
        }
        if min(
            values["campaign_limit_minor"],
            values["tenant_daily_limit_minor"],
            values["approval_required_minor"],
        ) < 0:
            raise ValueError("budget values cannot be negative")
        if not 1 <= values["max_attempts"] <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        existing = self.store.list(
            "generation_budget_policies",
            {"tenant_id": tenant_id, "campaign_id": campaign_id},
        )
        if existing:
            return self.store.update(
                "generation_budget_policies", existing[0]["id"], values
            )
        return self.store.create("generation_budget_policies", values)

    def policy_for(self, request: dict[str, Any]) -> dict[str, Any]:
        rows = self.store.list(
            "generation_budget_policies",
            {
                "tenant_id": request["tenant_id"],
                "campaign_id": request["campaign_id"],
            },
        )
        if not rows:
            raise RuntimeError("generation budget policy is required before costing")
        return rows[0]

    def _usage(
        self,
        *,
        tenant_id: str,
        campaign_id: str | None = None,
        spend_date: str | None = None,
    ) -> int:
        where = ["tenant_id=?"]
        args: list[Any] = [tenant_id]
        if campaign_id is not None:
            where.append("campaign_id=?")
            args.append(campaign_id)
        if spend_date is not None:
            where.append("spend_date=?")
            args.append(spend_date)
        rows = self.store.conn.execute(
            f"""SELECT event_type, amount_minor
                FROM generation_spend_ledger
                WHERE {' AND '.join(where)}""",
            args,
        ).fetchall()
        total = 0
        for row in rows:
            amount = int(row["amount_minor"])
            if row["event_type"] in {"RESERVED", "CHARGED"}:
                total += amount
            elif row["event_type"] == "RELEASED":
                total -= amount
        return max(0, total)

    def evaluate(
        self,
        request: dict[str, Any],
        estimate_minor: int,
        currency: str,
        exponent: int,
    ) -> dict[str, Any]:
        policy = self.policy_for(request)
        if (
            policy["currency"] != currency
            or int(policy["currency_minor_exponent"]) != int(exponent)
        ):
            raise ValueError("generation estimate currency does not match budget policy")
        campaign_used = self._usage(
            tenant_id=request["tenant_id"], campaign_id=request["campaign_id"]
        )
        tenant_daily_used = self._usage(
            tenant_id=request["tenant_id"], spend_date=_today_utc()
        )
        projected_campaign = campaign_used + int(estimate_minor)
        projected_daily = tenant_daily_used + int(estimate_minor)
        campaign_over = projected_campaign > int(policy["campaign_limit_minor"])
        daily_over = projected_daily > int(policy["tenant_daily_limit_minor"])
        allowed = not (campaign_over or daily_over)
        if (campaign_over or daily_over) and not bool(policy["hard_cap"]):
            allowed = True
        return {
            "allowed": allowed,
            "hard_cap": bool(policy["hard_cap"]),
            "approval_required": int(estimate_minor)
            >= int(policy["approval_required_minor"]),
            "campaign_used_minor": campaign_used,
            "tenant_daily_used_minor": tenant_daily_used,
            "projected_campaign_minor": projected_campaign,
            "projected_tenant_daily_minor": projected_daily,
            "campaign_limit_minor": int(policy["campaign_limit_minor"]),
            "tenant_daily_limit_minor": int(policy["tenant_daily_limit_minor"]),
            "max_attempts": int(policy["max_attempts"]),
            "currency": policy["currency"],
            "currency_minor_exponent": int(policy["currency_minor_exponent"]),
        }

    def reserve(self, request: dict[str, Any]) -> dict[str, Any]:
        existing = self.store.list(
            "generation_spend_ledger",
            {"request_id": request["id"], "event_type": "RESERVED"},
        )
        if existing:
            return existing[0]
        estimate = request.get("estimated_cost_minor")
        if estimate is None or not request.get("currency"):
            raise ValueError("request must be costed before budget reservation")
        evaluation = self.evaluate(
            request,
            int(estimate),
            str(request["currency"]),
            int(request["currency_minor_exponent"]),
        )
        if not evaluation["allowed"]:
            raise PermissionError("generation hard budget cap exceeded")
        return self.store.create(
            "generation_spend_ledger",
            {
                "request_id": request["id"],
                "tenant_id": request["tenant_id"],
                "campaign_id": request["campaign_id"],
                "event_type": "RESERVED",
                "amount_minor": int(estimate),
                "currency": request["currency"],
                "spend_date": _today_utc(),
            },
        )

    def settle(
        self, request: dict[str, Any], actual_minor: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        charged = self.store.list(
            "generation_spend_ledger",
            {"request_id": request["id"], "event_type": "CHARGED"},
        )
        released = self.store.list(
            "generation_spend_ledger",
            {"request_id": request["id"], "event_type": "RELEASED"},
        )
        if charged and released:
            return charged[0], released[0]
        reserved = self.store.list(
            "generation_spend_ledger",
            {"request_id": request["id"], "event_type": "RESERVED"},
        )
        if not reserved:
            raise ValueError("cannot settle generation without a reservation")
        estimate = int(reserved[0]["amount_minor"])
        if actual_minor > estimate:
            raise RuntimeError(
                "actual generation spend exceeded conservative reservation"
            )
        charge = self.store.create(
            "generation_spend_ledger",
            {
                "request_id": request["id"],
                "tenant_id": request["tenant_id"],
                "campaign_id": request["campaign_id"],
                "event_type": "CHARGED",
                "amount_minor": int(actual_minor),
                "currency": request["currency"],
                "spend_date": _today_utc(),
            },
        )
        release = self.store.create(
            "generation_spend_ledger",
            {
                "request_id": request["id"],
                "tenant_id": request["tenant_id"],
                "campaign_id": request["campaign_id"],
                "event_type": "RELEASED",
                "amount_minor": estimate,
                "currency": request["currency"],
                "spend_date": _today_utc(),
            },
        )
        return charge, release

    def release_failure(self, request: dict[str, Any]) -> dict[str, Any] | None:
        reserved = self.store.list(
            "generation_spend_ledger",
            {"request_id": request["id"], "event_type": "RESERVED"},
        )
        if not reserved:
            return None
        existing = self.store.list(
            "generation_spend_ledger",
            {"request_id": request["id"], "event_type": "RELEASED"},
        )
        if existing:
            return existing[0]
        return self.store.create(
            "generation_spend_ledger",
            {
                "request_id": request["id"],
                "tenant_id": request["tenant_id"],
                "campaign_id": request["campaign_id"],
                "event_type": "RELEASED",
                "amount_minor": int(reserved[0]["amount_minor"]),
                "currency": request["currency"],
                "spend_date": _today_utc(),
            },
        )


class GenerationOrchestrator:
    def __init__(
        self,
        store: CreativeOSStore,
        *,
        model_router: GenerationModelRouter | None = None,
        budget_guard: BudgetGuard | None = None,
    ):
        self.store = store
        self.router = model_router or GenerationModelRouter()
        self.budget = budget_guard or BudgetGuard(store)

    def get_request(self, request_id: str, tenant_id: str) -> dict[str, Any]:
        request = self.store.get("generation_requests", request_id)
        if request["tenant_id"] != tenant_id:
            raise PermissionError("generation request does not belong to tenant")
        return request

    @staticmethod
    def _approved_claims(brand: dict[str, Any]) -> list[str]:
        claims: list[str] = []
        for key in ("core_promise", "positioning", "elevator_pitch"):
            value = str(brand.get(key) or "").strip()
            if value:
                claims.append(value)
        for key in ("messaging_json", "proof_points_json"):
            value = brand.get(key) or []
            if isinstance(value, list):
                claims.extend(str(item).strip() for item in value if str(item).strip())
        return claims

    @classmethod
    def compile_brand_prompt(
        cls, original_prompt: str, brand: dict[str, Any]
    ) -> str:
        approved_claims = cls._approved_claims(brand)
        prohibited = brand.get("prohibited_messaging_json") or []
        prohibited_terms = brand.get("prohibited_terms_json") or []
        payload = {
            "brand": brand.get("display_name") or brand.get("name"),
            "positioning": brand.get("positioning") or "",
            "target_market": brand.get("target_market")
            or brand.get("audience")
            or "",
            "tone": brand.get("tone_of_voice") or "",
            "approved_claims": approved_claims,
            "prohibited_messaging": prohibited,
            "prohibited_terms": prohibited_terms,
        }
        return (
            original_prompt.strip()
            + "\n\nCREATIVEOS BRAND BRAIN — TRUSTED CONSTRAINTS\n"
            + _canonical(payload)
            + "\nUse only the approved claims above. Do not invent metrics, customers, "
            "performance guarantees, awards, integrations, or product capabilities."
        )

    def create_request(
        self,
        *,
        asset_requirement_id: str,
        tenant_id: str,
        user_id: str,
        idempotency_key: str,
        intent: str,
        original_prompt: str,
        business_claims: list[str] | None = None,
        parent_asset_id: str | None = None,
    ) -> dict[str, Any]:
        if not all(
            str(value or "").strip()
            for value in (tenant_id, user_id, idempotency_key, intent, original_prompt)
        ):
            raise ValueError("tenant, user, idempotency key, intent, and prompt are required")
        existing = self.store.list(
            "generation_requests",
            {"tenant_id": tenant_id, "idempotency_key": idempotency_key},
        )
        if existing:
            current = existing[0]
            if (
                current["asset_requirement_id"] != asset_requirement_id
                or current["original_prompt"] != original_prompt.strip()
            ):
                raise ValueError("idempotency key is already bound to another request")
            return current
        requirement = self.store.get("asset_requirements", asset_requirement_id)
        scene = self.store.get("scenes", requirement["scene_id"])
        board = self.store.get("storyboards", scene["storyboard_id"])
        campaign = self.store.get("campaigns", board["campaign_id"])
        brand = BrandBrainService(self.store).get(campaign["brand_profile_id"])
        capability = str(requirement["asset_type"]).lower().strip()
        if bool(scene.get("immutable_ui")) and capability in {"image", "video"}:
            raise PermissionError("immutable UI cannot enter generative routing")
        claims = [str(item).strip() for item in (business_claims or []) if str(item).strip()]
        approved_claims = {item.casefold() for item in self._approved_claims(brand)}
        unsupported_claims = [item for item in claims if item.casefold() not in approved_claims]
        if unsupported_claims:
            raise ValueError(
                "business claims must be explicitly approved in Brand Brain: "
                + ", ".join(unsupported_claims)
            )
        request = self.store.create(
            "generation_requests",
            {
                "asset_requirement_id": asset_requirement_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "campaign_id": campaign["id"],
                "brand_profile_id": brand["id"],
                "parent_asset_id": parent_asset_id,
                "intent": intent.upper().strip(),
                "capability": capability,
                "lifecycle_step": 0,
                "lifecycle_state": "DRAFT",
                "idempotency_key": idempotency_key,
                "original_prompt": original_prompt.strip(),
                "compiled_prompt": self.compile_brand_prompt(original_prompt, brand),
                "brand_snapshot_json": brand,
                "business_claims_json": claims,
            },
        )
        self.store.create(
            "generation_lifecycle_events",
            {
                "request_id": request["id"],
                "lifecycle_step": 0,
                "lifecycle_state": "DRAFT",
                "actor": user_id,
                "evidence_json": {"idempotency_key": idempotency_key},
            },
        )
        return request

    def _advance(
        self, request_id: str, actor: str, evidence: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        conn = self.store.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            raw = conn.execute(
                "SELECT * FROM generation_requests WHERE id=?", (request_id,)
            ).fetchone()
            if raw is None:
                raise KeyError(f"generation_requests:{request_id}")
            request = dict(raw)
            step = int(request["lifecycle_step"])
            next_step = step + 1
            if next_step >= len(LIFECYCLE):
                raise ValueError("generation lifecycle is already terminal")
            next_state = LIFECYCLE[next_step]
            stamp = now_iso()
            conn.execute(
                """UPDATE generation_requests
                   SET lifecycle_step=?, lifecycle_state=?, updated_at=? WHERE id=?""",
                (next_step, next_state, stamp, request_id),
            )
            conn.execute(
                """INSERT INTO generation_lifecycle_events(
                   id,request_id,lifecycle_step,lifecycle_state,actor,evidence_json,created_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                (
                    str(uuid4()), request_id, next_step, next_state,
                    actor, _canonical(evidence or {}), stamp,
                ),
            )
            conn.commit()
            return self.store.get("generation_requests", request_id)
        except Exception:
            conn.rollback()
            raise

    def plan(
        self,
        request_id: str,
        *,
        actor: str,
        duration_seconds: int | None = None,
        aspect_ratio: str = "9:16",
        references: list[dict[str, Any]] | None = None,
        explicit_premium_tier: bool = False,
        script: str = "",
        storyboard: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        request = self.store.get("generation_requests", request_id)
        if int(request["lifecycle_step"]) != 0:
            raise ValueError("only DRAFT requests may be planned")
        plan = {
            "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio,
            "references": references or [],
            "explicit_premium_tier": bool(explicit_premium_tier),
            "script": script,
            "storyboard": storyboard or [],
        }
        self.store.update("generation_requests", request_id, {"plan_json": plan})
        return self._advance(request_id, actor, {"plan": plan})

    def cost(self, request_id: str, *, actor: str) -> dict[str, Any]:
        request = self.store.get("generation_requests", request_id)
        if int(request["lifecycle_step"]) != 1:
            raise ValueError("only PLANNED requests may be costed")
        plan = _decode(request["plan_json"], {})
        references = plan.get("references") or []
        route = self.router.route(
            request["intent"],
            duration_seconds=plan.get("duration_seconds"),
            aspect_ratio=plan.get("aspect_ratio") or "9:16",
            has_references=bool(references),
            explicit_premium_tier=bool(plan.get("explicit_premium_tier")),
        )
        if route.capability != request["capability"]:
            raise ValueError("route capability does not match asset requirement")
        evaluation = self.budget.evaluate(
            request, route.estimated_cost_minor,
            route.currency, route.currency_minor_exponent,
        )
        self.store.update(
            "generation_requests",
            request_id,
            {
                "route_json": route.snapshot(),
                "estimated_cost_minor": route.estimated_cost_minor,
                "currency": route.currency,
                "currency_minor_exponent": route.currency_minor_exponent,
                "approval_required": int(bool(evaluation["approval_required"])),
            },
        )
        return self._advance(
            request_id, actor,
            {"route": route.snapshot(), "budget": evaluation,
             "cost_source": route.cost_source},
        )
    def record_approval(
        self,
        request_id: str,
        *,
        approval_type: str,
        approved_by: str,
        note: str,
        decision: str = "APPROVED",
    ) -> dict[str, Any]:
        approval_type = approval_type.upper().strip()
        decision = decision.upper().strip()
        existing = self.store.list(
            "generation_approvals",
            {"request_id": request_id, "approval_type": approval_type},
        )
        if existing:
            row = existing[0]
            if row["decision"] != decision:
                raise ValueError("approval decision is immutable")
            return row
        return self.store.create(
            "generation_approvals",
            {
                "request_id": request_id,
                "approval_type": approval_type,
                "decision": decision,
                "approved_by": approved_by,
                "note": note,
            },
        )

    def approve_cost(
        self,
        request_id: str,
        *,
        approved_by: str,
        note: str,
    ) -> dict[str, Any]:
        request = self.store.get("generation_requests", request_id)
        if int(request["lifecycle_step"]) != 2:
            raise ValueError("only COSTED requests may be approved")
        route = _decode(request["route_json"], {})
        evaluation = self.budget.evaluate(
            request,
            int(request["estimated_cost_minor"]),
            request["currency"],
            int(request["currency_minor_exponent"]),
        )
        if not evaluation["allowed"]:
            raise PermissionError("generation hard budget cap exceeded")
        if bool(request["approval_required"]):
            approval = self.store.list(
                "generation_approvals",
                {"request_id": request_id, "approval_type": "BUDGET"},
            )
            if not approval or approval[0]["decision"] != "APPROVED":
                raise PermissionError("explicit budget approval is required")
        if bool(route.get("premium")):
            approval = self.store.list(
                "generation_approvals",
                {"request_id": request_id, "approval_type": "PREMIUM"},
            )
            if not approval or approval[0]["decision"] != "APPROVED":
                raise PermissionError("explicit premium-render approval is required")
        self.budget.reserve(request)
        return self._advance(
            request_id, approved_by,
            {"budget": evaluation, "approval_note": note},
        )

    def queue_request(self, request_id: str, *, actor: str) -> dict[str, Any]:
        request = self.store.get("generation_requests", request_id)
        if int(request["lifecycle_step"]) != 3:
            raise ValueError("only pre-generation APPROVED requests may be queued")
        route = _decode(request["route_json"], {})
        plan = _decode(request["plan_json"], {})
        requirement = self.store.get(
            "asset_requirements", request["asset_requirement_id"]
        )
        job = self.store.create(
            "generation_jobs",
            {
                "scene_id": requirement["scene_id"],
                "asset_requirement_id": request["asset_requirement_id"],
                "provider": route["provider"],
                "model": route["model"],
                "state": "QUEUED",
                "request_json": {
                    "generation_request_id": request_id,
                    "route": route,
                    "plan": plan,
                },
                "prompt": request["compiled_prompt"],
                "negative_prompt": "",
                "reference_assets_json": plan.get("references") or [],
                "aspect_ratio": plan.get("aspect_ratio") or "",
                "duration_seconds": plan.get("duration_seconds"),
                "cost_credit_json": {
                    "estimated_cost_minor": request["estimated_cost_minor"],
                    "currency": request["currency"],
                    "currency_minor_exponent": request["currency_minor_exponent"],
                    "source": route.get("cost_source"),
                },
                "provider_snapshot": route["provider"],
                "model_snapshot": route["model"],
            },
        )
        self.store.update(
            "generation_requests", request_id, {"generation_job_id": job["id"]}
        )
        policy = self.budget.policy_for(request)
        queue = GenerationQueueService(self.store).enqueue(
            job["id"], max_attempts=int(policy["max_attempts"])
        )
        updated = self._advance(
            request_id, actor,
            {"generation_job_id": job["id"], "queue_id": queue["id"]},
        )
        return {"request": updated, "job": job, "queue": queue}

    def begin_qa(self, request_id: str, *, actor: str) -> dict[str, Any]:
        request = self.store.get("generation_requests", request_id)
        if int(request["lifecycle_step"]) != 6:
            raise ValueError("only GENERATED requests may enter QA")
        return self._advance(request_id, actor, {})

    def complete_qa(self, request_id: str, *, actor: str) -> dict[str, Any]:
        request = self.store.get("generation_requests", request_id)
        if int(request["lifecycle_step"]) != 7:
            raise ValueError("request is not at QA stage")
        gate = self.store.list("generation_gate_runs", {"request_id": request_id})
        if not gate or gate[0]["result"] != "PASS":
            raise PermissionError("generation QA gate must PASS before human review")
        return self._advance(
            request_id, actor, {"generation_gate_id": gate[0]["id"]}
        )

    def human_approve(
        self, request_id: str, *, approved_by: str, note: str
    ) -> dict[str, Any]:
        request = self.store.get("generation_requests", request_id)
        if int(request["lifecycle_step"]) != 8:
            raise ValueError("request is not ready for human review")
        self.record_approval(
            request_id,
            approval_type="HUMAN_REVIEW",
            approved_by=approved_by,
            note=note,
        )
        return self._advance(request_id, approved_by, {"note": note})
    def create_export(
        self,
        request_id: str,
        *,
        render_job_id: str,
        qa_run_id: str,
        actor: str,
        preset: str = "META_REEL_9_16",
    ) -> dict[str, Any]:
        request = self.store.get("generation_requests", request_id)
        if int(request["lifecycle_step"]) != 9:
            raise PermissionError("human approval is required before export")
        render = self.store.get("render_jobs", render_job_id)
        qa = self.store.get("qa_runs", qa_run_id)
        if qa["render_job_id"] != render_job_id or qa["overall_result"] != "PASS":
            raise PermissionError("render QA must PASS before export")
        reviews = self.store.list("qa_reviews", {"qa_run_id": qa_run_id})
        if not reviews or reviews[0]["review_state"] != "ACCEPTED":
            raise PermissionError("render QA human review must be accepted")
        export = self.store.create(
            "export_jobs",
            {
                "campaign_id": request["campaign_id"],
                "preset": preset,
                "state": "APPROVED",
                "output_path": render["output_path"],
                "settings_json": {
                    "generation_request_id": request_id,
                    "render_job_id": render_job_id,
                    "qa_run_id": qa_run_id,
                    "auto_publish": False,
                },
            },
        )
        ready = self._advance(
            request_id, actor,
            {"export_job_id": export["id"], "auto_publish": False},
        )
        return {"request": ready, "export": export}


class HiggsfieldGenerationWorker:
    def __init__(
        self,
        store: CreativeOSStore,
        provider: HiggsfieldProvider,
        output_root: str | Path,
        *,
        worker_id: str = "higgsfield-worker",
        orchestrator: GenerationOrchestrator | None = None,
    ):
        self.store = store
        self.provider = provider
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.worker_id = worker_id
        self.orchestrator = orchestrator or GenerationOrchestrator(store)
        self.queue = GenerationQueueService(store)

    def _last_attempt(self, request_id: str) -> dict[str, Any] | None:
        rows = self.store.list("generation_attempts", {"request_id": request_id})
        if not rows:
            return None
        return sorted(rows, key=lambda row: int(row["attempt_number"]))[-1]

    def _new_attempt(
        self, request: dict[str, Any], route: dict[str, Any], plan: dict[str, Any]
    ) -> dict[str, Any]:
        prior = self._last_attempt(request["id"])
        attempt_number = 1 if prior is None else int(prior["attempt_number"]) + 1
        policy = self.orchestrator.budget.policy_for(request)
        if attempt_number > int(policy["max_attempts"]):
            raise RuntimeError("generation max attempts reached")
        return self.store.create(
            "generation_attempts",
            {
                "request_id": request["id"],
                "attempt_number": attempt_number,
                "provider": route["provider"],
                "model": route["model"],
                "state": "SUBMITTING",
                "correlation_id": f"creativeos-{request['id']}-{attempt_number}",
                "compiled_prompt": request["compiled_prompt"],
                "settings_json": route["settings"],
                "references_json": plan.get("references") or [],
                "estimated_cost_minor": int(request["estimated_cost_minor"]),
                "currency": request["currency"],
                "currency_minor_exponent": int(request["currency_minor_exponent"]),
            },
        )

    def _provider_input(
        self, request: dict[str, Any], route: dict[str, Any], plan: dict[str, Any]
    ) -> dict[str, Any]:
        decision = RouteDecision(
            provider=route["provider"],
            model=route["model"],
            capability=route["capability"],
            intent=route["intent"],
            settings=route["settings"],
            estimated_cost_minor=int(route["estimated_cost_minor"]),
            currency=route["currency"],
            currency_minor_exponent=int(route["currency_minor_exponent"]),
            premium=bool(route["premium"]),
            cost_source=route["cost_source"],
        )
        return self.orchestrator.router.provider_input(
            decision,
            request["compiled_prompt"],
            plan.get("references") or [],
        )

    def _save_output(
        self, request: dict[str, Any], payload: bytes
    ) -> tuple[Path, str]:
        suffix = ".mp4" if request["capability"] == "video" else ".png"
        folder = self.output_root / _safe_component(request["id"])
        folder.mkdir(parents=True, exist_ok=True)
        path = (folder / f"provider-output{suffix}").resolve()
        if self.output_root not in path.parents:
            raise ValueError("generation output path escaped approved root")
        path.write_bytes(payload)
        return path, hashlib.sha256(payload).hexdigest()

    def execute_request(self, request_id: str) -> dict[str, Any]:
        request = self.store.get("generation_requests", request_id)
        if int(request["lifecycle_step"]) not in {4, 5}:
            raise ValueError("request must be QUEUED or GENERATING")
        if not request.get("generation_job_id"):
            raise ValueError("generation request is missing legacy job authority")
        queue = self.queue.claim_job(
            request["generation_job_id"], self.worker_id, lease_seconds=120
        )
        if queue is None:
            existing = self.store.list(
                "generation_results", {"request_id": request_id}
            )
            if existing:
                return existing[0]
            raise RuntimeError("generation job is not currently claimable")
        running = self.queue.start(queue["id"], queue["claim_token"])
        if running["state"] == "CANCELLED":
            return running
        if int(request["lifecycle_step"]) == 4:
            request = self.orchestrator._advance(
                request_id, self.worker_id,
                {"queue_id": queue["id"], "worker_id": self.worker_id},
            )
        self.store.update(
            "generation_jobs",
            request["generation_job_id"],
            {"state": "RUNNING", "error": None},
        )
        route = _decode(request["route_json"], {})
        plan = _decode(request["plan_json"], {})
        attempt = self._last_attempt(request_id)
        if attempt and attempt["state"] == "SUBMIT_UNCERTAIN":
            self.queue._finish(
                queue["id"], "FAILED", "SUBMIT_UNCERTAIN",
                "operator reconciliation required; submit was not repeated",
            )
            return attempt
        if not attempt or attempt["state"] in {"FAILED", "CANCELLED", "REJECTED"}:
            attempt = self._new_attempt(request, route, plan)

        submission: HiggsfieldSubmission
        if attempt.get("provider_request_id"):
            submission = HiggsfieldSubmission(
                request_id=attempt["provider_request_id"],
                status="in_progress",
                status_url=attempt["provider_status_url"],
                cancel_url=attempt.get("provider_cancel_url"),
                raw={},
            )
        else:
            try:
                submission = self.provider.submit(
                    route["model"],
                    self._provider_input(request, route, plan),
                    correlation_id=attempt["correlation_id"],
                )
                attempt = self.store.update(
                    "generation_attempts",
                    attempt["id"],
                    {
                        "state": "SUBMITTED",
                        "provider_request_id": submission.request_id,
                        "provider_status_url": submission.status_url,
                        "provider_cancel_url": submission.cancel_url,
                        "submitted_at": now_iso(),
                        "retryable": 0,
                        "error_code": None,
                        "error_message": None,
                    },
                )
                self.store.update(
                    "generation_jobs",
                    request["generation_job_id"],
                    {
                        "response_json": {
                            "provider_request_id": submission.request_id,
                            "status_url": submission.status_url,
                        }
                    },
                )
            except HiggsfieldProviderError as exc:
                state = "SUBMIT_UNCERTAIN" if exc.submit_uncertain else "FAILED"
                attempt = self.store.update(
                    "generation_attempts",
                    attempt["id"],
                    {
                        "state": state,
                        "retryable": int(exc.retryable),
                        "error_code": exc.code,
                        "error_message": str(exc),
                        "completed_at": now_iso(),
                    },
                )
                if exc.submit_uncertain or not exc.retryable:
                    self.store.update(
                        "generation_jobs", request["generation_job_id"],
                        {"state": "FAILED", "error": str(exc)},
                    )
                    self.queue._finish(
                        queue["id"], "FAILED", exc.code, str(exc)
                    )
                    if not exc.submit_uncertain:
                        self.orchestrator.budget.release_failure(request)
                    return attempt
                self.store.update(
                    "generation_jobs", request["generation_job_id"],
                    {"state": "QUEUED", "error": str(exc)},
                )
                self.queue.fail_or_retry(
                    queue["id"], queue["claim_token"],
                    exc.code, str(exc), backoff_seconds=4,
                )
                return attempt
        def on_status(payload: dict[str, Any]) -> None:
            self.store.update(
                "generation_attempts",
                attempt["id"],
                {
                    "state": "POLLING",
                    "error_code": None,
                    "error_message": None,
                },
            )

        try:
            final = self.provider.poll(submission, on_status=on_status)
            output_bytes = self.provider.download(final.output_url)
        except HiggsfieldProviderError as exc:
            current = self.store.get("generation_attempts", attempt["id"])
            if exc.code == "POLL_TIMEOUT" and current.get("provider_request_id"):
                self.store.update(
                    "generation_attempts",
                    attempt["id"],
                    {
                        "state": "POLLING",
                        "retryable": 1,
                        "error_code": exc.code,
                        "error_message": str(exc),
                    },
                )
                self.store.update(
                    "generation_jobs", request["generation_job_id"],
                    {"state": "QUEUED", "error": str(exc)},
                )
                self.queue.fail_or_retry(
                    queue["id"], queue["claim_token"],
                    exc.code, str(exc), backoff_seconds=4,
                )
                return self.store.get("generation_attempts", attempt["id"])
            self.store.update(
                "generation_attempts",
                attempt["id"],
                {
                    "state": "FAILED",
                    "retryable": int(exc.retryable),
                    "error_code": exc.code,
                    "error_message": str(exc),
                    "completed_at": now_iso(),
                },
            )
            self.store.update(
                "generation_jobs", request["generation_job_id"],
                {"state": "FAILED", "error": str(exc)},
            )
            if exc.retryable:
                self.store.update(
                    "generation_jobs", request["generation_job_id"],
                    {"state": "QUEUED"},
                )
                self.queue.fail_or_retry(
                    queue["id"], queue["claim_token"],
                    exc.code, str(exc), backoff_seconds=4,
                )
            else:
                self.queue._finish(
                    queue["id"], "FAILED", exc.code, str(exc)
                )
                self.orchestrator.budget.release_failure(request)
            return self.store.get("generation_attempts", attempt["id"])

        local_path, checksum = self._save_output(request, output_bytes)
        provider_actual = final.raw.get("actual_cost_minor")
        if isinstance(provider_actual, int) and provider_actual >= 0:
            actual_minor = provider_actual
            actual_source = "PROVIDER_RESPONSE"
        else:
            actual_minor = int(request["estimated_cost_minor"])
            actual_source = "COMPLETED_LIST_RATE_SNAPSHOT"
        attempt = self.store.update(
            "generation_attempts",
            attempt["id"],
            {
                "state": "SUCCEEDED",
                "actual_cost_minor": actual_minor,
                "actual_cost_source": actual_source,
                "retryable": 0,
                "error_code": None,
                "error_message": None,
                "completed_at": now_iso(),
            },
        )
        generated_asset = self.store.create(
            "generated_assets",
            {
                "generation_job_id": request["generation_job_id"],
                "asset_requirement_id": request["asset_requirement_id"],
                "output_path": str(local_path),
                "output_type": request["capability"],
                "output_metadata_json": {
                    "provider_request_id": final.request_id,
                    "provider_output_url": final.output_url,
                    "provider_status": final.status,
                },
                "prompt_snapshot": request["compiled_prompt"],
                "provider_snapshot": route["provider"],
                "model_snapshot": route["model"],
                "checksum_sha256": checksum,
                "review_state": "PENDING",
            },
        )
        result = self.store.create(
            "generation_results",
            {
                "request_id": request_id,
                "attempt_id": attempt["id"],
                "provider_request_id": final.request_id,
                "output_url": final.output_url,
                "local_path": str(local_path),
                "output_type": request["capability"],
                "output_metadata_json": {
                    "provider_status": final.status,
                    "generated_asset_id": generated_asset["id"],
                },
                "checksum_sha256": checksum,
                "estimated_cost_minor": int(request["estimated_cost_minor"]),
                "actual_cost_minor": actual_minor,
                "actual_cost_source": actual_source,
                "currency": request["currency"],
                "currency_minor_exponent": int(request["currency_minor_exponent"]),
            },
        )
        self.store.create(
            "generation_provenance",
            {
                "result_id": result["id"],
                "request_id": request_id,
                "tenant_id": request["tenant_id"],
                "user_id": request["user_id"],
                "campaign_id": request["campaign_id"],
                "brand_profile_id": request["brand_profile_id"],
                "parent_asset_id": request.get("parent_asset_id"),
                "original_prompt": request["original_prompt"],
                "compiled_provider_prompt": request["compiled_prompt"],
                "provider": route["provider"],
                "model": route["model"],
                "settings_json": route["settings"],
                "references_json": plan.get("references") or [],
                "estimated_cost_minor": int(request["estimated_cost_minor"]),
                "actual_cost_minor": actual_minor,
                "actual_cost_source": actual_source,
                "currency": request["currency"],
                "currency_minor_exponent": int(request["currency_minor_exponent"]),
                "provider_request_id": final.request_id,
            },
        )
        self.orchestrator.budget.settle(request, actual_minor)
        self.store.update(
            "generation_requests", request_id,
            {"actual_cost_minor": actual_minor},
        )
        self.store.update(
            "generation_jobs",
            request["generation_job_id"],
            {
                "state": "SUCCEEDED",
                "output_path": str(local_path),
                "actual_cost_cents": actual_minor,
                "response_json": {
                    "provider_request_id": final.request_id,
                    "status": final.status,
                    "output_url": final.output_url,
                },
                "error": None,
            },
        )
        self.queue._finish(queue["id"], "SUCCEEDED")
        self.orchestrator._advance(
            request_id,
            self.worker_id,
            {
                "generation_result_id": result["id"],
                "generated_asset_id": generated_asset["id"],
                "provider_request_id": final.request_id,
            },
        )
        return result


RELEASE_CHECKS = (
    "TENANT_OWNERSHIP",
    "SERVER_SECRET_BOUNDARY",
    "BRAND_BINDING",
    "RENDER_DIMENSIONS_DURATION",
    "PROVENANCE_COMPLETE",
    "BUDGET_ENFORCED",
    "RETRY_BOUNDED",
    "DUPLICATE_PREVENTION",
    "NO_FABRICATED_CLAIMS",
    "NO_PUBLICATION_WITHOUT_APPROVAL",
)


class GenerationReleaseGate:
    def __init__(self, store: CreativeOSStore):
        self.store = store

    @staticmethod
    def _sensitive_keys(value: Any) -> bool:
        forbidden = {
            "authorization", "api_key", "api_secret",
            "credentials", "secret",
        }
        if isinstance(value, dict):
            for key, nested in value.items():
                if (
                    str(key).lower() in forbidden
                    or GenerationReleaseGate._sensitive_keys(nested)
                ):
                    return True
        elif isinstance(value, list):
            return any(
                GenerationReleaseGate._sensitive_keys(item)
                for item in value
            )
        return False

    @staticmethod
    def _claim_set(brand: dict[str, Any]) -> set[str]:
        return {
            item.strip().casefold()
            for item in GenerationOrchestrator._approved_claims(brand)
            if item.strip()
        }

    def run(
        self, request_id: str, *, render_qa_run_id: str
    ) -> dict[str, Any]:
        existing = self.store.list(
            "generation_gate_runs", {"request_id": request_id}
        )
        if existing:
            return existing[0]
        request = self.store.get("generation_requests", request_id)
        if int(request["lifecycle_step"]) != 7:
            raise ValueError("generation request must be at QA stage")
        result_rows = self.store.list(
            "generation_results", {"request_id": request_id}
        )
        provenance_rows = self.store.list(
            "generation_provenance", {"request_id": request_id}
        )
        attempts = self.store.list(
            "generation_attempts", {"request_id": request_id}
        )
        policy_rows = self.store.list(
            "generation_budget_policies",
            {
                "tenant_id": request["tenant_id"],
                "campaign_id": request["campaign_id"],
            },
        )
        render_qa = self.store.get("qa_runs", render_qa_run_id)
        campaign = self.store.get("campaigns", request["campaign_id"])
        brand = _decode(request["brand_snapshot_json"], {})
        claims = _decode(request["business_claims_json"], [])
        result = result_rows[0] if result_rows else {}
        provenance = provenance_rows[0] if provenance_rows else {}
        policy = policy_rows[0] if policy_rows else {}
        ledger = self.store.list(
            "generation_spend_ledger", {"request_id": request_id}
        )
        event_types = {row["event_type"] for row in ledger}
        provider_ids = [
            row["provider_request_id"]
            for row in attempts
            if row.get("provider_request_id")
        ]
        persisted_payload = {
            "request": {
                "route": _decode(request["route_json"], {}),
                "plan": _decode(request["plan_json"], {}),
            },
            "attempts": [
                {
                    "settings": _decode(row["settings_json"], {}),
                    "references": _decode(row["references_json"], []),
                }
                for row in attempts
            ],
            "provenance": {
                "settings": _decode(provenance.get("settings_json"), {}),
                "references": _decode(provenance.get("references_json"), []),
            },
        }
        budget_ok = (
            bool(policy)
            and event_types == {"RESERVED", "CHARGED", "RELEASED"}
        )
        if budget_ok:
            guard = BudgetGuard(self.store)
            campaign_usage = guard._usage(
                tenant_id=request["tenant_id"],
                campaign_id=request["campaign_id"],
            )
            daily_usage = guard._usage(
                tenant_id=request["tenant_id"],
                spend_date=_today_utc(),
            )
            budget_ok = (
                campaign_usage <= int(policy["campaign_limit_minor"])
                and daily_usage <= int(policy["tenant_daily_limit_minor"])
                and int(result.get("actual_cost_minor", -1))
                <= int(result.get("estimated_cost_minor", -2))
            )
        approved_claims = self._claim_set(brand)
        claims_ok = all(
            str(claim).strip().casefold() in approved_claims
            for claim in claims
        )
        checks = {
            "TENANT_OWNERSHIP": bool(result)
            and bool(provenance)
            and provenance.get("tenant_id") == request["tenant_id"]
            and provenance.get("campaign_id") == request["campaign_id"],
            "SERVER_SECRET_BOUNDARY": not self._sensitive_keys(
                persisted_payload
            ),
            "BRAND_BINDING":
                campaign["brand_profile_id"] == request["brand_profile_id"]
                and provenance.get("brand_profile_id")
                == request["brand_profile_id"],
            "RENDER_DIMENSIONS_DURATION":
                render_qa["overall_result"] == "PASS"
                and render_qa["lifecycle_state"] == "FINALIZED",
            "PROVENANCE_COMPLETE": bool(provenance)
            and all(
                provenance.get(key)
                for key in (
                    "original_prompt",
                    "compiled_provider_prompt",
                    "provider",
                    "model",
                    "provider_request_id",
                )
            ),
            "BUDGET_ENFORCED": budget_ok,
            "RETRY_BOUNDED": bool(policy)
            and 1 <= len(attempts) <= int(policy["max_attempts"])
            and not any(
                row["state"] == "SUBMIT_UNCERTAIN" for row in attempts
            ),
            "DUPLICATE_PREVENTION":
                len(provider_ids) == len(set(provider_ids))
                and len(result_rows) == 1,
            "NO_FABRICATED_CLAIMS": claims_ok,
            "NO_PUBLICATION_WITHOUT_APPROVAL":
                int(request["lifecycle_step"]) == 7
                and not self.store.list(
                    "generation_approvals",
                    {
                        "request_id": request_id,
                        "approval_type": "HUMAN_REVIEW",
                    },
                ),
        }
        evidence = [
            {
                "check_id": check_id,
                "result": "PASS" if checks[check_id] else "FAIL",
            }
            for check_id in RELEASE_CHECKS
        ]
        overall = "PASS" if all(checks.values()) else "FAIL"
        return self.store.create(
            "generation_gate_runs",
            {
                "request_id": request_id,
                "result": overall,
                "checks_json": evidence,
            },
        )
