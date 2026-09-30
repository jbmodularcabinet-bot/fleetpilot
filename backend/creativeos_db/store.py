from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .migrations import MIGRATIONS
from .scope_schema import GLOBAL_TABLES, SCOPED_TABLES
from .brand_brain import validate_brand_payload

TABLES = {
    "organizations", "brand_profiles", "campaigns", "storyboards", "scenes", "assets",
    "generation_jobs", "qa_results", "export_jobs", "creative_memory", "director_plans", "scene_versions",
    "asset_requirements", "generated_assets", "generation_queue",
    "provider_cost_profiles", "fx_snapshots", "cost_recommendations", "cost_estimates", "cost_overrides",
    "voice_jobs", "composition_timelines", "composition_timeline_entries", "render_jobs", "render_attempts",
    "qa_runs", "qa_check_results", "qa_reviews",
    "generation_requests", "generation_lifecycle_events", "generation_attempts",
    "generation_results", "generation_provenance", "generation_budget_policies",
    "generation_spend_ledger", "generation_approvals", "generation_gate_runs",
}
JSON_FIELDS = {
    "brand_profiles": {"palette_json", "fonts_json", "messaging_json", "cta_rules_json", "prohibited_visuals_json", "approved_refs_json", "immutable_rules_json", "pain_points_json", "proof_points_json", "prohibited_messaging_json", "preferred_terms_json", "prohibited_terms_json", "campaign_languages_json", "approved_ui_folders_json", "protected_screens_json", "allowed_ui_transforms_json", "prohibited_generative_transforms_json", "visual_rules_json"},
    "generation_jobs": {"request_json", "response_json", "reference_assets_json", "cost_credit_json"},
    "generated_assets": {"output_metadata_json"},
    "cost_estimates": {"profile_snapshot_json", "fx_snapshot_json", "budget_snapshot_json", "calculation_json"},
    "cost_overrides": {"evidence_json"},
    "composition_timeline_entries": {"transition_json"},
    "render_jobs": {"command_args_json", "probe_json"},
    "qa_runs": {"required_checks_json"},
    "qa_check_results": {"expected_json", "observed_json", "evidence_json"},
    "generation_requests": {"brand_snapshot_json", "plan_json", "route_json", "business_claims_json"},
    "generation_lifecycle_events": {"evidence_json"},
    "generation_attempts": {"settings_json", "references_json"},
    "generation_results": {"output_metadata_json"},
    "generation_provenance": {"settings_json", "references_json"},
    "generation_gate_runs": {"checks_json"},
    "export_jobs": {"settings_json"},
    "director_plans": {"brief_json", "output_json"},
    "scenes": {"asset_requirements_json"},
    "scene_versions": {"asset_refs_json"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CreativeOSStore:
    def __init__(self, db_path: str | Path, *, organization_id: str | None = None,
                 brand_profile_id: str | None = None):
        # Unscoped connections are trusted local/admin infrastructure, not user APIs.
        if (organization_id is None) != (brand_profile_id is None):
            raise ValueError("organization and brand scope must be supplied together")
        self.scope = None if organization_id is None else (organization_id, brand_profile_id)
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        if self.scope is not None:
            try:
                self.get("brand_profiles", brand_profile_id)
            except Exception:
                self.conn.close()
                raise

    def scope_clause(self, table: str) -> tuple[str, tuple]:
        self._columns(table)
        if self.scope is None or table in GLOBAL_TABLES:
            return "1=1", ()
        if table == "organizations":
            return "id=?", (self.scope[0],)
        if table not in SCOPED_TABLES:
            raise PermissionError("table has no ownership mapping")
        return (f"id IN (SELECT id FROM v_scope_{table} WHERE organization_id=? AND brand_profile_id=?)",
                self.scope)

    def _assert_writable(self, table: str) -> None:
        if self.scope is not None and table in GLOBAL_TABLES | {"organizations"}:
            raise PermissionError("shared configuration requires an administrative connection")

    def _migration_script(self, script: str) -> None:
        try:
            self.conn.executescript("BEGIN IMMEDIATE;\n" + script + "\nCOMMIT;")
        except Exception:
            self.conn.rollback()
            raise

    def close(self) -> None:
        self.conn.close()

    def schema_version(self) -> int:
        row = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not row:
            return 0
        row = self.conn.execute("SELECT COALESCE(MAX(version),0) AS v FROM schema_migrations").fetchone()
        return int(row["v"])

    def migrate_to_latest(self) -> int:
        if self.scope is not None:
            raise PermissionError("schema changes require an administrative connection")
        current = self.schema_version()
        for version in sorted(MIGRATIONS):
            if version > current:
                self._migration_script(MIGRATIONS[version][0])
        return self.schema_version()

    def rollback_to(self, target_version: int) -> int:
        if self.scope is not None:
            raise PermissionError("schema changes require an administrative connection")
        current = self.schema_version()
        if current >= 11 and target_version < 11:
            if self.conn.execute("SELECT 1 FROM organizations LIMIT 1").fetchone():
                raise ValueError("rollback would discard organization ownership")
        for version in sorted(MIGRATIONS, reverse=True):
            if target_version < version <= current:
                self._migration_script(MIGRATIONS[version][1])
        return self.schema_version()

    def _encode(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        encoded = dict(values)
        for key in JSON_FIELDS.get(table, set()):
            if key in encoded and encoded[key] is not None and not isinstance(encoded[key], str):
                encoded[key] = json.dumps(encoded[key], sort_keys=True)
        if "immutable_ui" in encoded:
            encoded["immutable_ui"] = int(bool(encoded["immutable_ui"]))
        if "default_immutable_ui" in encoded:
            encoded["default_immutable_ui"] = int(bool(encoded["default_immutable_ui"]))
        for flag in ("locked","immutable_ui","is_selected","is_approved"):
            if flag in encoded: encoded[flag] = int(bool(encoded[flag]))
        return encoded
    def _columns(self, table: str) -> set[str]:
        if table not in TABLES:
            raise ValueError(f"unsupported table: {table}")
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    def create(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        self._assert_writable(table)
        columns = self._columns(table)
        if table == "brand_profiles":
            values = validate_brand_payload(values)
        data = self._encode(table, values)
        data.setdefault("id", str(uuid4()))
        stamp = now_iso()
        if "created_at" in columns:
            data.setdefault("created_at", stamp)
        if "updated_at" in columns:
            data.setdefault("updated_at", stamp)
        unknown = set(data) - columns
        if unknown:
            raise ValueError(f"unknown columns for {table}: {sorted(unknown)}")
        keys = list(data)
        placeholders = ",".join("?" for _ in keys)
        sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({placeholders})"
        try:
            self.conn.execute(sql, [data[k] for k in keys])
            result = self.get(table, data["id"])
            self.conn.commit()
            return result
        except Exception:
            self.conn.rollback()
            raise

    def get(self, table: str, row_id: str) -> dict[str, Any]:
        self._columns(table)
        row = self.conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
        if row is None:
            raise KeyError(f"{table}:{row_id}")
        clause, params = self.scope_clause(table)
        if not self.conn.execute(f"SELECT 1 FROM {table} WHERE id=? AND ({clause})",
                                 (row_id, *params)).fetchone():
            raise PermissionError("record is outside the active organization and brand")
        return dict(row)

    def list(self, table: str, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        columns = self._columns(table)
        where = where or {}
        unknown = set(where) - columns
        if unknown:
            raise ValueError(f"unknown filters for {table}: {sorted(unknown)}")
        scope_clause, scope_params = self.scope_clause(table)
        clause = " AND ".join([*(f"{key}=?" for key in where), f"({scope_clause})"])
        sql = f"SELECT * FROM {table} WHERE {clause}"
        if table == "scenes":
            sql += " ORDER BY position ASC"
        rows = self.conn.execute(sql, [*where.values(), *scope_params]).fetchall()
        return [dict(row) for row in rows]
    def update(self, table: str, row_id: str, values: dict[str, Any]) -> dict[str, Any]:
        self._assert_writable(table)
        self.get(table, row_id)
        if table in {"generated_assets", "provider_cost_profiles", "fx_snapshots", "cost_recommendations", "cost_estimates", "cost_overrides", "qa_runs", "qa_check_results", "qa_reviews", "generation_lifecycle_events", "generation_results", "generation_provenance", "generation_spend_ledger", "generation_approvals", "generation_gate_runs"}:
            raise ValueError(f"{table} records are immutable")
        columns = self._columns(table)
        if table == "brand_profiles":
            current = self.get(table, row_id)
            merged = dict(current)
            merged.update(values)
            values = validate_brand_payload(merged)
        data = self._encode(table, values)
        data.pop("id", None)
        if "updated_at" in columns:
            data["updated_at"] = now_iso()
        unknown = set(data) - columns
        if unknown:
            raise ValueError(f"unknown columns for {table}: {sorted(unknown)}")
        if not data:
            return self.get(table, row_id)
        assignments = ",".join(f"{key}=?" for key in data)
        try:
            self.conn.execute(f"UPDATE {table} SET {assignments} WHERE id=?",
                              [*data.values(), row_id])
            result = self.get(table, row_id)
            self.conn.commit()
            return result
        except Exception:
            self.conn.rollback()
            raise

    def delete(self, table: str, row_id: str) -> None:
        self._assert_writable(table)
        self.get(table, row_id)
        if table in {"generated_assets", "provider_cost_profiles", "fx_snapshots", "cost_recommendations", "cost_estimates", "cost_overrides", "qa_runs", "qa_check_results", "qa_reviews", "generation_lifecycle_events", "generation_results", "generation_provenance", "generation_spend_ledger", "generation_approvals", "generation_gate_runs"}:
            raise ValueError(f"{table} records are immutable")
        self._columns(table)
        cur = self.conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
        if cur.rowcount == 0:
            self.conn.rollback()
            raise KeyError(f"{table}:{row_id}")
        self.conn.commit()

    def foreign_key_violations(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("PRAGMA foreign_key_check").fetchall()
        return [dict(row) for row in rows]

    def __enter__(self) -> "CreativeOSStore":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
