import json
import sqlite3

import unittest
from test_authenticated_scope import AuthFixture
from creativeos_db import CreativeOSStore
from creativeos_db.adoption import AdoptionService
from creativeos_db.auth import AccessError


class LegacyAdoptionTests(AuthFixture, unittest.TestCase):
    def legacy(self, name="Unowned"):
        with CreativeOSStore(self.db) as store:
            brand = store.create("brand_profiles", {"name": name, "core_promise": "Preserve this evidence"})
            campaign = store.create("campaigns", {"brand_profile_id": brand["id"], "title": "Legacy"})
        return brand, campaign

    def test_preview_confirmation_is_explicit_atomic_and_audited(self):
        brand, campaign = self.legacy()
        self.select()
        with self.request(write=True) as ctx:
            service = AdoptionService(ctx)
            preview = service.preview(brand["id"])
            self.assertEqual(preview["conflicts"], [])
            self.assertEqual(preview["organization_id"], self.orgs[0]["id"])
        with CreativeOSStore(self.db) as store:
            self.assertIsNone(store.get("campaigns", campaign["id"])["organization_id"])
        with self.request(write=True) as ctx:
            with self.assertRaises(ValueError):
                AdoptionService(ctx).confirm(preview["id"], preview["digest"], False)
        with self.request(write=True) as ctx:
            receipt = AdoptionService(ctx).confirm(preview["id"], preview["digest"], True)
        with CreativeOSStore(self.db) as store:
            self.assertEqual(store.get("campaigns", campaign["id"])["organization_id"], self.orgs[0]["id"])
            self.assertEqual(store.get("brand_profiles", brand["id"])["core_promise"], "Preserve this evidence")
            audit = store.conn.execute("SELECT * FROM ownership_audit WHERE id=?", (receipt["audit_id"],)).fetchone()
            self.assertEqual(audit["actor_id"], self.users[0]["id"])
            self.assertIsNone(json.loads(audit["before_json"])["brand"]["organization_id"])
            self.assertEqual(store.conn.execute("SELECT count(*) FROM adoption_permits").fetchone()[0], 0)
            with self.assertRaises(sqlite3.IntegrityError):
                store.conn.execute("DELETE FROM ownership_audit")
        with self.request(write=True) as ctx:
            with self.assertRaises(AccessError):
                AdoptionService(ctx).confirm(preview["id"], preview["digest"], True)

    def test_ordinary_org_owner_cannot_discover_or_adopt_unowned_data(self):
        brand, _ = self.legacy()
        self.select(1)
        with self.request(1, write=True) as ctx:
            with self.assertRaises(AccessError):
                AdoptionService(ctx).inventory()
            with self.assertRaises(AccessError):
                AdoptionService(ctx).preview(brand["id"])

    def test_preview_digest_conflicts_and_scope_switch_rejected(self):
        brand, campaign = self.legacy()
        self.select()
        with self.request(write=True) as ctx:
            preview = AdoptionService(ctx).preview(brand["id"])
        with CreativeOSStore(self.db) as store:
            store.update("campaigns", campaign["id"], {"title": "Changed after preview"})
        with self.request(write=True) as ctx:
            with self.assertRaises(AccessError):
                AdoptionService(ctx).confirm(preview["id"], preview["digest"], True)
        with CreativeOSStore(self.db) as store:
            self.assertIsNone(store.get("brand_profiles", brand["id"])["organization_id"])
            self.assertEqual(store.conn.execute("SELECT count(*) FROM ownership_audit").fetchone()[0], 0)

    def test_duplicate_name_never_silently_adopted(self):
        duplicate, _ = self.legacy(self.brands[0]["name"])
        self.select()
        with self.request(write=True) as ctx:
            preview = AdoptionService(ctx).preview(duplicate["id"])
            self.assertTrue(preview["conflicts"])
            with self.assertRaises(AccessError):
                AdoptionService(ctx).confirm(preview["id"], preview["digest"], True)

    def test_contradictory_tenant_labels_block_adoption(self):
        from creativeos_db.generation_engine import BudgetGuard
        brand, campaign = self.legacy()
        with CreativeOSStore(self.db) as store:
            second = store.create("campaigns", {"brand_profile_id": brand["id"], "title": "Other legacy"})
            for label, c in zip(("legacy-a", "legacy-b"), (campaign, second)):
                BudgetGuard(store).set_policy(label, c["id"], campaign_limit_minor=100,
                    tenant_daily_limit_minor=100, approval_required_minor=10)
        self.select()
        with self.request(write=True) as ctx:
            service = AdoptionService(ctx)
            preview = service.preview(brand["id"])
            self.assertTrue(any("Contradictory" in c for c in preview["conflicts"]))
            with self.assertRaises(AccessError):
                service.confirm(preview["id"], preview["digest"], True)

    def test_adoption_normalizes_legacy_tenant_metadata_and_keeps_before_audit(self):
        from creativeos_db.generation_engine import BudgetGuard
        brand, campaign = self.legacy()
        with CreativeOSStore(self.db) as store:
            BudgetGuard(store).set_policy("legacy-owner-label", campaign["id"], campaign_limit_minor=100,
                tenant_daily_limit_minor=100, approval_required_minor=10)
        self.select()
        with self.request(write=True) as ctx:
            service = AdoptionService(ctx)
            preview = service.preview(brand["id"])
            receipt = service.confirm(preview["id"], preview["digest"], True)
        with CreativeOSStore(self.db) as store:
            policy = store.conn.execute("SELECT tenant_id FROM generation_budget_policies WHERE campaign_id=?", (campaign["id"],)).fetchone()
            self.assertEqual(policy[0], self.orgs[0]["id"])
            before = json.loads(store.conn.execute("SELECT before_json FROM ownership_audit WHERE id=?", (receipt["audit_id"],)).fetchone()[0])
            self.assertEqual(before["records"]["generation_budget_policies"][0]["tenant_id"], "legacy-owner-label")

    def test_adoption_failure_rolls_back_ownership_permit_and_audit(self):
        brand, campaign = self.legacy()
        self.select()
        with self.request(write=True) as ctx:
            preview = AdoptionService(ctx).preview(brand["id"])
        with self.assertRaisesRegex(RuntimeError, "later failure"):
            with self.request(write=True) as ctx:
                AdoptionService(ctx).confirm(preview["id"], preview["digest"], True)
                raise RuntimeError("later failure")
        with CreativeOSStore(self.db) as store:
            self.assertIsNone(store.get("brand_profiles", brand["id"])["organization_id"])
            self.assertIsNone(store.get("campaigns", campaign["id"])["organization_id"])
            self.assertEqual(store.conn.execute("SELECT count(*) FROM ownership_audit").fetchone()[0], 0)
            self.assertEqual(store.conn.execute("SELECT count(*) FROM adoption_permits").fetchone()[0], 0)
            self.assertEqual(store.conn.execute("SELECT consumed FROM adoption_previews WHERE id=?", (preview["id"],)).fetchone()[0], 0)

    def test_preview_cannot_survive_scope_change_or_expiry_or_another_login(self):
        brand, _ = self.legacy()
        self.select()
        with self.request(write=True) as ctx:
            preview = AdoptionService(ctx).preview(brand["id"])
        login = self.auth.login("alice", "test-password-only-123")
        self.auth.select_scope(login["token"], login["csrf"], 0, self.orgs[0]["id"], self.brands[0]["id"])
        with self.auth.request(login["token"], expected_version=1, csrf=login["csrf"], write=True) as ctx:
            with self.assertRaises(AccessError):
                AdoptionService(ctx).confirm(preview["id"], preview["digest"], True)
        a = self.logins[0]
        self.auth.select_scope(a["token"], a["csrf"], 1, self.orgs[0]["id"], self.brands[0]["id"])
        with self.request(version=2, write=True) as ctx:
            with self.assertRaises(AccessError):
                AdoptionService(ctx).confirm(preview["id"], preview["digest"], True)
            current = AdoptionService(ctx).preview(brand["id"])
        with CreativeOSStore(self.db) as store:
            store.conn.execute("UPDATE adoption_previews SET expires_at=0 WHERE id=?", (current["id"],))
            store.conn.commit()
        with self.request(version=2, write=True) as ctx:
            with self.assertRaises(AccessError):
                AdoptionService(ctx).confirm(current["id"], current["digest"], True)

    def test_ambiguous_legacy_parent_links_block_confirmation(self):
        brand, campaign = self.legacy()
        other, other_campaign = self.legacy("Other legacy")
        with CreativeOSStore(self.db) as store:
            board = store.create("storyboards", {"campaign_id": other_campaign["id"], "title": "Legacy board"})
            scene = store.create("scenes", {"storyboard_id": board["id"], "position": 1, "title": "Legacy scene", "duration_seconds": 2})
            # Reproduce a pre-v11 inconsistent row, then restore every current guard.
            triggers = store.conn.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='assets'").fetchall()
            for trigger in triggers:
                store.conn.execute('DROP TRIGGER "' + trigger["name"] + '"')
            store.create("assets", {"campaign_id": campaign["id"], "scene_id": scene["id"], "asset_type": "image", "path": "legacy.png"})
            for trigger in triggers:
                store.conn.execute(trigger["sql"])
            store.conn.commit()
        self.select()
        with self.request(write=True) as ctx:
            service = AdoptionService(ctx)
            preview = service.preview(brand["id"])
            self.assertTrue(any("Ambiguous assets" in conflict for conflict in preview["conflicts"]))
            with self.assertRaises(AccessError):
                service.confirm(preview["id"], preview["digest"], True)


if __name__ == "__main__":
    import unittest
    unittest.main()
