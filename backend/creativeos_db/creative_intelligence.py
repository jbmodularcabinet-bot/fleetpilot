from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .store import CreativeOSStore, now_iso

EVIDENCE_STATES = {"INSUFFICIENT", "LIMITED", "MODERATE", "STRONG"}
TRUTH_LEVELS = {"REAL_PROJECT", "APPROVED_RENDER", "AI_DERIVED", "AI_GENERATED"}
REFERENCE_FIDELITY = {"NONE", "LOW", "MEDIUM", "HIGH", "EXACT"}
MARKET_TYPES = {"PAIN_POINT", "TRIGGER", "OBJECTION", "PROOF", "COMPETITOR_PATTERN"}
SUBJECT_TYPES = {"BRAND", "PRODUCT", "SERVICE"}
HYPOTHESIS_STATUS = {"DRAFT", "READY", "EXPERIMENTING", "ARCHIVED"}
EXPERIMENT_STATUS = {"DRAFT", "READY", "RUNNING", "PAUSED", "COMPLETED", "ARCHIVED"}
ASSET_KINDS = {"ASSET": "assets", "GENERATED_ASSET": "generated_assets"}
TEXT_LIMIT = 4000


def _text(value: Any, field: str, *, required: bool = False, limit: int = TEXT_LIMIT) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{field} is required")
    if len(value) > limit:
        raise ValueError(f"{field} is too long")
    return value


def _enum(value: Any, field: str, allowed: set[str], *, default: str | None = None) -> str:
    if value in (None, "") and default is not None:
        value = default
    value = _text(value, field, required=True, limit=80).upper()
    if value not in allowed:
        raise ValueError(f"invalid {field}")
    return value


def _payload(value: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unsupported fields: {sorted(unknown)}")
    return dict(value)


class CreativeIntelligenceService:
    def __init__(self, store: CreativeOSStore):
        if store.scope is None:
            raise PermissionError("creative intelligence requires an active organization and brand")
        self.store = store
        self.organization_id, self.brand_profile_id = store.scope

    def _get(self, table: str, row_id: str) -> dict[str, Any]:
        row = self.store.conn.execute(
            f"""SELECT * FROM {table}
                WHERE id=? AND organization_id=? AND brand_profile_id=?""",
            (row_id, self.organization_id, self.brand_profile_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"{table}:{row_id}")
        return dict(row)

    def _list(self, table: str, *, extra: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        rows = self.store.conn.execute(
            f"""SELECT * FROM {table}
                WHERE organization_id=? AND brand_profile_id=? {extra}
                ORDER BY created_at DESC""",
            (self.organization_id, self.brand_profile_id, *params),
        ).fetchall()
        return [dict(row) for row in rows]

    def _insert(self, table: str, values: dict[str, Any], *, updated: bool = True) -> dict[str, Any]:
        stamp = now_iso()
        data = {
            "id": str(uuid4()),
            "organization_id": self.organization_id,
            "brand_profile_id": self.brand_profile_id,
            **values,
            "created_at": stamp,
        }
        if updated:
            data["updated_at"] = stamp
        keys = list(data)
        self.store.conn.execute(
            f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
            [data[key] for key in keys],
        )
        self.store.conn.commit()
        return self._get(table, data["id"])

    def _update(self, table: str, row_id: str, values: dict[str, Any]) -> dict[str, Any]:
        self._get(table, row_id)
        if not values:
            return self._get(table, row_id)
        values = {**values, "updated_at": now_iso()}
        assignments = ",".join(f"{key}=?" for key in values)
        self.store.conn.execute(
            f"""UPDATE {table} SET {assignments}
                WHERE id=? AND organization_id=? AND brand_profile_id=?""",
            [*values.values(), row_id, self.organization_id, self.brand_profile_id],
        )
        self.store.conn.commit()
        return self._get(table, row_id)

    def _delete(self, table: str, row_id: str) -> None:
        self._get(table, row_id)
        cursor = self.store.conn.execute(
            f"DELETE FROM {table} WHERE id=? AND organization_id=? AND brand_profile_id=?",
            (row_id, self.organization_id, self.brand_profile_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"{table}:{row_id}")
        self.store.conn.commit()

    def create_market_intelligence(self, values: dict[str, Any]) -> dict[str, Any]:
        values = _payload(values, {
            "subject", "subject_type", "intelligence_type", "evidence_source", "notes", "active",
        })
        data = {
            "subject": _text(values.get("subject"), "subject", required=True),
            "subject_type": _enum(values.get("subject_type"), "subject_type", SUBJECT_TYPES),
            "intelligence_type": _enum(values.get("intelligence_type"), "intelligence_type", MARKET_TYPES),
            "evidence_source": _text(values.get("evidence_source"), "evidence_source"),
            "notes": _text(values.get("notes"), "notes"),
            "active": int(bool(values.get("active", True))),
        }
        return self._insert("market_intelligence", data)

    def update_market_intelligence(self, row_id: str, values: dict[str, Any]) -> dict[str, Any]:
        values = _payload(values, {
            "subject", "subject_type", "intelligence_type", "evidence_source", "notes", "active",
        })
        data: dict[str, Any] = {}
        if "subject" in values:
            data["subject"] = _text(values["subject"], "subject", required=True)
        if "subject_type" in values:
            data["subject_type"] = _enum(values["subject_type"], "subject_type", SUBJECT_TYPES)
        if "intelligence_type" in values:
            data["intelligence_type"] = _enum(values["intelligence_type"], "intelligence_type", MARKET_TYPES)
        for field in ("evidence_source", "notes"):
            if field in values:
                data[field] = _text(values[field], field)
        if "active" in values:
            data["active"] = int(bool(values["active"]))
        return self._update("market_intelligence", row_id, data)

    def list_market_intelligence(self) -> list[dict[str, Any]]:
        return self._list("market_intelligence")

    def delete_market_intelligence(self, row_id: str) -> None:
        self._delete("market_intelligence", row_id)

    _HYPOTHESIS_FIELDS = {
        "objective", "audience", "pain_point", "offer", "angle", "hook", "proof", "cta",
        "format", "funnel_stage", "platform", "success_metric", "evidence_state",
        "unresolved_assumptions", "status",
    }

    def _hypothesis_values(self, values: dict[str, Any], *, creating: bool) -> dict[str, Any]:
        values = _payload(values, self._HYPOTHESIS_FIELDS)
        data: dict[str, Any] = {}
        for field in (
            "objective", "audience", "pain_point", "offer", "angle", "hook", "proof", "cta",
            "format", "funnel_stage", "platform", "success_metric", "unresolved_assumptions",
        ):
            if field in values or (creating and field == "objective"):
                data[field] = _text(values.get(field), field, required=field == "objective")
        if "evidence_state" in values:
            data["evidence_state"] = _enum(values["evidence_state"], "evidence_state", EVIDENCE_STATES)
        elif creating:
            data["evidence_state"] = "INSUFFICIENT"
        if "status" in values:
            data["status"] = _enum(values["status"], "status", HYPOTHESIS_STATUS)
        elif creating:
            data["status"] = "DRAFT"
        return data

    def create_hypothesis(self, values: dict[str, Any]) -> dict[str, Any]:
        return self._insert("creative_hypotheses", self._hypothesis_values(values, creating=True))

    def update_hypothesis(self, row_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return self._update("creative_hypotheses", row_id, self._hypothesis_values(values, creating=False))

    def get_hypothesis(self, row_id: str) -> dict[str, Any]:
        result = self._get("creative_hypotheses", row_id)
        result["evidence"] = self.list_evidence(row_id)
        return result

    def list_hypotheses(self) -> list[dict[str, Any]]:
        rows = self._list("creative_hypotheses")
        for row in rows:
            row["evidence"] = self.list_evidence(row["id"])
        return rows

    def delete_hypothesis(self, row_id: str) -> None:
        self._delete("creative_hypotheses", row_id)

    _REFERENCE_FIELDS = {
        "reference_source", "hook_pattern", "offer_pattern", "composition_pattern",
        "proof_mechanism", "cta_pattern", "format", "audience_stage",
        "brand_safe_adaptation_notes",
    }

    def _reference_values(self, values: dict[str, Any], *, creating: bool) -> dict[str, Any]:
        values = _payload(values, self._REFERENCE_FIELDS)
        data: dict[str, Any] = {}
        for field in self._REFERENCE_FIELDS:
            if field in values or (creating and field == "reference_source"):
                data[field] = _text(
                    values.get(field), field, required=field == "reference_source",
                )
        return data

    def create_reference_pattern(self, values: dict[str, Any]) -> dict[str, Any]:
        return self._insert("reference_patterns", self._reference_values(values, creating=True))

    def update_reference_pattern(self, row_id: str, values: dict[str, Any]) -> dict[str, Any]:
        return self._update("reference_patterns", row_id, self._reference_values(values, creating=False))

    def list_reference_patterns(self) -> list[dict[str, Any]]:
        return self._list("reference_patterns")

    def delete_reference_pattern(self, row_id: str) -> None:
        self._delete("reference_patterns", row_id)

    def create_experiment(self, values: dict[str, Any]) -> dict[str, Any]:
        values = _payload(values, {
            "hypothesis_id", "variant", "campaign_external_id", "ad_external_id", "status",
        })
        hypothesis_id = _text(values.get("hypothesis_id"), "hypothesis_id", required=True, limit=200)
        self._get("creative_hypotheses", hypothesis_id)
        data = {
            "hypothesis_id": hypothesis_id,
            "variant": _text(values.get("variant"), "variant", required=True),
            "campaign_external_id": _text(values.get("campaign_external_id"), "campaign_external_id", limit=300),
            "ad_external_id": _text(values.get("ad_external_id"), "ad_external_id", limit=300),
            "status": _enum(values.get("status"), "status", EXPERIMENT_STATUS, default="DRAFT"),
        }
        return self._insert("experiments", data)

    def update_experiment(self, row_id: str, values: dict[str, Any]) -> dict[str, Any]:
        values = _payload(values, {"variant", "campaign_external_id", "ad_external_id", "status"})
        data: dict[str, Any] = {}
        for field in ("variant", "campaign_external_id", "ad_external_id"):
            if field in values:
                data[field] = _text(values[field], field, required=field == "variant", limit=TEXT_LIMIT)
        if "status" in values:
            data["status"] = _enum(values["status"], "status", EXPERIMENT_STATUS)
        return self._update("experiments", row_id, data)

    def list_experiments(self) -> list[dict[str, Any]]:
        rows = self._list("experiments")
        for row in rows:
            row["assets"] = self.list_experiment_assets(row["id"])
        return rows

    def delete_experiment(self, row_id: str) -> None:
        self._delete("experiments", row_id)

    def add_evidence(self, values: dict[str, Any]) -> dict[str, Any]:
        values = _payload(values, {
            "hypothesis_id", "market_intelligence_id", "source", "source_url",
            "observation", "sample_size", "evidence_strength",
        })
        hypothesis_id = _text(values.get("hypothesis_id"), "hypothesis_id", required=True, limit=200)
        self._get("creative_hypotheses", hypothesis_id)
        market_id = values.get("market_intelligence_id") or None
        if market_id is not None:
            market_id = _text(market_id, "market_intelligence_id", required=True, limit=200)
            self._get("market_intelligence", market_id)
        sample_size = values.get("sample_size")
        if sample_size in ("", None):
            sample_size = None
        elif type(sample_size) is not int or sample_size < 0:
            raise ValueError("sample_size must be a non-negative integer")
        data = {
            "hypothesis_id": hypothesis_id,
            "market_intelligence_id": market_id,
            "source": _text(values.get("source"), "source", required=True),
            "source_url": _text(values.get("source_url"), "source_url", limit=2000),
            "observation": _text(values.get("observation"), "observation", required=True),
            "sample_size": sample_size,
            "evidence_strength": _enum(
                values.get("evidence_strength"), "evidence_strength", EVIDENCE_STATES, default="LIMITED",
            ),
        }
        return self._insert("hypothesis_evidence", data, updated=False)

    def list_evidence(self, hypothesis_id: str) -> list[dict[str, Any]]:
        self._get("creative_hypotheses", hypothesis_id)
        return self._list("hypothesis_evidence", extra="AND hypothesis_id=?", params=(hypothesis_id,))

    def delete_evidence(self, row_id: str) -> None:
        self._delete("hypothesis_evidence", row_id)

    def link_experiment_asset(self, experiment_id: str, asset_id: str, asset_kind: str = "ASSET") -> dict[str, Any]:
        experiment = self._get("experiments", experiment_id)
        kind = _enum(asset_kind, "asset_kind", set(ASSET_KINDS))
        asset = self.store.get(ASSET_KINDS[kind], _text(asset_id, "asset_id", required=True, limit=200))
        data = {
            "id": str(uuid4()),
            "organization_id": self.organization_id,
            "brand_profile_id": self.brand_profile_id,
            "experiment_id": experiment["id"],
            "asset_kind": kind,
            "asset_id": asset["id"],
            "created_at": now_iso(),
        }
        keys = list(data)
        self.store.conn.execute(
            f"INSERT INTO experiment_asset_links ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
            [data[key] for key in keys],
        )
        self.store.conn.commit()
        return dict(data)

    def list_experiment_assets(self, experiment_id: str) -> list[dict[str, Any]]:
        self._get("experiments", experiment_id)
        rows = self.store.conn.execute(
            """SELECT * FROM experiment_asset_links
               WHERE experiment_id=? AND organization_id=? AND brand_profile_id=?
               ORDER BY created_at DESC""",
            (experiment_id, self.organization_id, self.brand_profile_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def unlink_experiment_asset(self, link_id: str) -> None:
        self._delete("experiment_asset_links", link_id)

    def set_asset_provenance(
        self, asset_id: str, *, truth_level: str | None, reference_fidelity_required: bool,
    ) -> dict[str, Any]:
        truth = None if truth_level in (None, "") else _enum(truth_level, "truth_level", TRUTH_LEVELS)
        return self.store.update(
            "assets", asset_id,
            {
                "truth_level": truth,
                "reference_fidelity_required": int(bool(reference_fidelity_required)),
            },
        )

    def list_provider_capabilities(self) -> list[dict[str, Any]]:
        rows = self.store.conn.execute(
            """SELECT * FROM generation_provider_capabilities
               ORDER BY provider, model"""
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["supported_job_types"] = json.loads(item.pop("supported_job_types_json"))
            item["estimated_cost_metadata"] = json.loads(item.pop("estimated_cost_metadata_json"))
            item["enabled"] = bool(item["enabled"])
            result.append(item)
        return result

    def overview(self) -> dict[str, Any]:
        assets = []
        for kind, table in ASSET_KINDS.items():
            for row in self.store.list(table):
                path = row.get("path") or row.get("output_path") or ""
                assets.append({
                    "id": row["id"],
                    "asset_kind": kind,
                    "asset_type": row.get("asset_type") or "generated",
                    "label": Path(str(path)).name or row["id"],
                    "truth_level": row.get("truth_level"),
                    "reference_fidelity_required": bool(row.get("reference_fidelity_required", 0)),
                })
        return {
            "market_intelligence": self.list_market_intelligence(),
            "hypotheses": self.list_hypotheses(),
            "reference_patterns": self.list_reference_patterns(),
            "experiments": self.list_experiments(),
            "assets": assets,
            "provider_capabilities": self.list_provider_capabilities(),
        }


class ProviderCapabilityRegistry:
    def __init__(self, store: CreativeOSStore):
        if store.scope is not None:
            raise PermissionError("provider capability registry requires administrative scope")
        self.store = store

    def upsert(self, values: dict[str, Any]) -> dict[str, Any]:
        values = _payload(values, {
            "provider", "model", "supported_job_types", "estimated_cost_metadata",
            "reference_fidelity_capability", "enabled",
        })
        provider = _text(values.get("provider"), "provider", required=True, limit=120)
        model = _text(values.get("model"), "model", required=True, limit=240)
        job_types = values.get("supported_job_types")
        if not isinstance(job_types, list) or not job_types or any(
            not isinstance(item, str) or not item.strip() or len(item.strip()) > 80
            for item in job_types
        ):
            raise ValueError("supported_job_types must be a non-empty text list")
        cost = values.get("estimated_cost_metadata", {})
        if not isinstance(cost, dict):
            raise ValueError("estimated_cost_metadata must be an object")
        fidelity = _enum(
            values.get("reference_fidelity_capability"),
            "reference_fidelity_capability",
            REFERENCE_FIDELITY,
            default="NONE",
        )
        stamp = now_iso()
        existing = self.store.conn.execute(
            "SELECT id,created_at FROM generation_provider_capabilities WHERE provider=? AND model=?",
            (provider, model),
        ).fetchone()
        row_id = existing["id"] if existing else str(uuid4())
        created_at = existing["created_at"] if existing else stamp
        self.store.conn.execute(
            """INSERT INTO generation_provider_capabilities(
                 id,provider,model,supported_job_types_json,estimated_cost_metadata_json,
                 reference_fidelity_capability,enabled,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(provider,model) DO UPDATE SET
                 supported_job_types_json=excluded.supported_job_types_json,
                 estimated_cost_metadata_json=excluded.estimated_cost_metadata_json,
                 reference_fidelity_capability=excluded.reference_fidelity_capability,
                 enabled=excluded.enabled,
                 updated_at=excluded.updated_at""",
            (
                row_id, provider, model, json.dumps(sorted({item.strip() for item in job_types})),
                json.dumps(cost, sort_keys=True), fidelity, int(bool(values.get("enabled", False))),
                created_at, stamp,
            ),
        )
        self.store.conn.commit()
        row = self.store.conn.execute(
            "SELECT * FROM generation_provider_capabilities WHERE provider=? AND model=?",
            (provider, model),
        ).fetchone()
        result = dict(row)
        result["supported_job_types"] = json.loads(result.pop("supported_job_types_json"))
        result["estimated_cost_metadata"] = json.loads(result.pop("estimated_cost_metadata_json"))
        result["enabled"] = bool(result["enabled"])
        return result

    def list(self) -> list[dict[str, Any]]:
        rows = self.store.conn.execute(
            "SELECT * FROM generation_provider_capabilities ORDER BY provider,model"
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["supported_job_types"] = json.loads(item.pop("supported_job_types_json"))
            item["estimated_cost_metadata"] = json.loads(item.pop("estimated_cost_metadata_json"))
            item["enabled"] = bool(item["enabled"])
            result.append(item)
        return result
