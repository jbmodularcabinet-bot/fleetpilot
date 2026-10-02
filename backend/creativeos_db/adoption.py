from __future__ import annotations

import hashlib
import json
import time
from uuid import uuid4

from .auth import AccessError
from .scope_schema import PARENTS, SCOPED_TABLES
from .store import now_iso


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class AdoptionService:
    """Platform-admin + target-org-owner, whole legacy brand aggregate adoption."""
    def __init__(self, context):
        self.ctx = context
        self.conn = context.store.conn
        if not context.platform_admin or context.role != "OWNER":
            raise AccessError("Legacy adoption requires platform administration and organization ownership")

    def inventory(self):
        brands = [dict(r) for r in self.conn.execute("""SELECT b.id,b.name,b.entity_type,
            (SELECT count(*) FROM campaigns c WHERE c.brand_profile_id=b.id) AS campaigns
            FROM brand_profiles b WHERE b.organization_id IS NULL ORDER BY b.name""")]
        orphan_assets = self.conn.execute("""SELECT count(*) FROM assets
            WHERE campaign_id IS NULL AND scene_id IS NULL""").fetchone()[0]
        return {"brands": brands, "unassigned_assets": orphan_assets,
                "notice": "Unbound assets require manual ownership investigation and are not adopted."}

    def _snapshot(self, brand_id):
        brand = self.conn.execute("SELECT * FROM brand_profiles WHERE id=?", (brand_id,)).fetchone()
        if not brand or brand["organization_id"] is not None:
            raise AccessError("Record is not an unowned legacy brand", 409, "ADOPTION_CONFLICT")
        records = {}
        for table in sorted(SCOPED_TABLES - {"brand_profiles"}):
            rows = self.conn.execute(f"""SELECT r.* FROM {table} r
                JOIN v_scope_{table} s ON s.id=r.id WHERE s.brand_profile_id=? ORDER BY r.id""", (brand_id,))
            records[table] = [dict(r) for r in rows]
        conflicts = []
        duplicate = self.conn.execute("""SELECT 1 FROM brand_profiles
            WHERE organization_id=? AND lower(name)=lower(?)""", (self.ctx.organization_id, brand["name"])).fetchone()
        if duplicate:
            conflicts.append("A brand with this name already exists in the destination organization.")
        for campaign in records["campaigns"]:
            if campaign["organization_id"] is not None:
                conflicts.append("A campaign already has ownership.")
        labels = sorted({r["tenant_id"] for table in (
            "generation_requests", "generation_provenance", "generation_budget_policies", "generation_spend_ledger")
            for r in records[table]})
        for request in records["generation_requests"]:
            collision = self.conn.execute("""SELECT 1 FROM generation_requests
                WHERE tenant_id=? AND idempotency_key=? AND id<>?""",
                (self.ctx.organization_id, request["idempotency_key"], request["id"])).fetchone()
            if collision:
                conflicts.append("Generation idempotency conflicts with destination records.")
        if len(labels) > 1:
            conflicts.append("Contradictory legacy tenant labels require manual investigation.")
        for table, rows in records.items():
            parents = PARENTS.get(table, [])
            if table == "assets":
                parents = [("campaign_id", "campaigns"), ("scene_id", "scenes")]
            for row in rows:
                for column, parent in parents:
                    if row.get(column) is None:
                        continue
                    owner = self.conn.execute(f"SELECT brand_profile_id FROM v_scope_{parent} WHERE id=?",
                                              (row[column],)).fetchone()
                    if not owner or owner["brand_profile_id"] != brand_id:
                        conflicts.append(f"Ambiguous {table} reference requires investigation.")
        if self.conn.execute("PRAGMA foreign_key_check").fetchone():
            conflicts.append("Unresolved database references require investigation.")
        return {"brand": dict(brand), "records": records, "legacy_tenant_labels": labels,
                "conflicts": sorted(set(conflicts))}

    def preview(self, brand_id):
        snapshot = self._snapshot(brand_id)
        digest = hashlib.sha256(canonical(snapshot).encode()).hexdigest()
        preview_id = str(uuid4())
        expires = int(time.time()) + 600
        self.conn.execute("""INSERT INTO adoption_previews
            (id,user_id,session_hash,organization_id,active_brand_id,scope_version,legacy_brand_id,
             snapshot_json,digest,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (preview_id, self.ctx.user_id, self.ctx.session_hash, self.ctx.organization_id,
             self.ctx.brand_profile_id, self.ctx.version, brand_id, canonical(snapshot), digest, expires))
        return {"id": preview_id, "digest": digest, "expires_at": expires,
                "organization_id": self.ctx.organization_id, "brand_id": brand_id,
                "brand_name": snapshot["brand"]["name"], "entity_type": snapshot["brand"]["entity_type"],
                "counts": {k: len(v) for k, v in snapshot["records"].items() if v},
                "legacy_tenant_labels": snapshot["legacy_tenant_labels"], "conflicts": snapshot["conflicts"],
                "notice": "The complete legacy brand moves to this organization. Brand content is preserved."}

    def confirm(self, preview_id, digest, confirmation):
        if confirmation is not True:
            raise ValueError("Explicit adoption confirmation is required")
        row = self.conn.execute("SELECT * FROM adoption_previews WHERE id=?", (preview_id,)).fetchone()
        if (not row or row["consumed"] or row["expires_at"] <= int(time.time())
            or row["user_id"] != self.ctx.user_id or row["session_hash"] != self.ctx.session_hash
            or row["organization_id"] != self.ctx.organization_id
            or row["active_brand_id"] != self.ctx.brand_profile_id
            or row["scope_version"] != self.ctx.version or row["digest"] != digest):
            raise AccessError("Adoption preview is stale or belongs to another context", 409, "ADOPTION_CONFLICT")
        before = self._snapshot(row["legacy_brand_id"])
        if before["conflicts"] or hashlib.sha256(canonical(before).encode()).hexdigest() != row["digest"]:
            raise AccessError("Legacy records changed or have ambiguous ownership; preview again", 409, "ADOPTION_CONFLICT")
        brand_id, org_id = row["legacy_brand_id"], self.ctx.organization_id
        self.conn.execute("INSERT INTO adoption_permits VALUES(?,?,?)", (brand_id, org_id, preview_id))
        self.conn.execute("UPDATE brand_profiles SET organization_id=? WHERE id=?", (org_id, brand_id))
        self.conn.execute("UPDATE campaigns SET organization_id=? WHERE brand_profile_id=?", (org_id, brand_id))
        # Normalize ownership metadata, preserving all prior values in immutable audit evidence.
        for table in ("generation_requests", "generation_provenance", "generation_budget_policies", "generation_spend_ledger"):
            for record in before["records"][table]:
                self.conn.execute(f"UPDATE {table} SET tenant_id=? WHERE id=?", (org_id, record["id"]))
        self.conn.execute("DELETE FROM adoption_permits WHERE brand_id=?", (brand_id,))
        if self.conn.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Adoption failed reference integrity")
        after = {"brand": dict(self.conn.execute("SELECT * FROM brand_profiles WHERE id=?", (brand_id,)).fetchone()),
                 "records": {}}
        for table, rows in before["records"].items():
            after["records"][table] = [dict(self.conn.execute(f"SELECT * FROM {table} WHERE id=?",
                                                             (r["id"],)).fetchone()) for r in rows]
        audit_id = str(uuid4())
        self.conn.execute("INSERT INTO ownership_audit VALUES(?,?,?,?,?,?,?,?)",
            (audit_id, preview_id, self.ctx.user_id, org_id, brand_id, canonical(before), canonical(after), now_iso()))
        self.conn.execute("UPDATE adoption_previews SET consumed=1 WHERE id=?", (preview_id,))
        return {"audit_id": audit_id, "organization_id": org_id, "brand_id": brand_id}
