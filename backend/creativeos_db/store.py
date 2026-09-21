from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .migrations import MIGRATIONS
from .brand_brain import validate_brand_payload

TABLES = {
    "brand_profiles", "campaigns", "storyboards", "scenes", "assets",
    "generation_jobs", "qa_results", "export_jobs", "creative_memory", "director_plans", "scene_versions",
    "asset_requirements", "generated_assets", "generation_queue",
}
JSON_FIELDS = {
    "brand_profiles": {"palette_json", "fonts_json", "messaging_json", "cta_rules_json", "prohibited_visuals_json", "approved_refs_json", "immutable_rules_json", "pain_points_json", "proof_points_json", "prohibited_messaging_json", "preferred_terms_json", "prohibited_terms_json", "campaign_languages_json", "approved_ui_folders_json", "protected_screens_json", "allowed_ui_transforms_json", "prohibited_generative_transforms_json", "visual_rules_json"},
    "generation_jobs": {"request_json", "response_json", "reference_assets_json", "cost_credit_json"},
    "generated_assets": {"output_metadata_json"},
    "export_jobs": {"settings_json"},
    "director_plans": {"brief_json", "output_json"},
    "scenes": {"asset_requirements_json"},
    "scene_versions": {"asset_refs_json"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CreativeOSStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
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
        current = self.schema_version()
        for version in sorted(MIGRATIONS):
            if version > current:
                self.conn.executescript(MIGRATIONS[version][0])
                self.conn.commit()
        return self.schema_version()

    def rollback_to(self, target_version: int) -> int:
        current = self.schema_version()
        for version in sorted(MIGRATIONS, reverse=True):
            if target_version < version <= current:
                self.conn.executescript(MIGRATIONS[version][1])
                self.conn.commit()
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
        self.conn.execute(sql, [data[k] for k in keys])
        self.conn.commit()
        return self.get(table, data["id"])

    def get(self, table: str, row_id: str) -> dict[str, Any]:
        self._columns(table)
        row = self.conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
        if row is None:
            raise KeyError(f"{table}:{row_id}")
        return dict(row)

    def list(self, table: str, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        columns = self._columns(table)
        where = where or {}
        unknown = set(where) - columns
        if unknown:
            raise ValueError(f"unknown filters for {table}: {sorted(unknown)}")
        clause = " AND ".join(f"{key}=?" for key in where)
        sql = f"SELECT * FROM {table}" + (f" WHERE {clause}" if clause else "")
        if table == "scenes":
            sql += " ORDER BY position ASC"
        rows = self.conn.execute(sql, list(where.values())).fetchall()
        return [dict(row) for row in rows]
    def update(self, table: str, row_id: str, values: dict[str, Any]) -> dict[str, Any]:
        if table == "generated_assets":
            raise ValueError("generated asset provenance is immutable")
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
        cur = self.conn.execute(
            f"UPDATE {table} SET {assignments} WHERE id=?",
            [*data.values(), row_id],
        )
        if cur.rowcount == 0:
            self.conn.rollback()
            raise KeyError(f"{table}:{row_id}")
        self.conn.commit()
        return self.get(table, row_id)

    def delete(self, table: str, row_id: str) -> None:
        if table == "generated_assets":
            raise ValueError("generated asset provenance is immutable")
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
