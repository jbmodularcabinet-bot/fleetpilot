import json
import unittest
from pathlib import Path

from test_authenticated_scope import AuthFixture
from creativeos_db.api import API


class AuthenticatedAPITests(AuthFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.api = API(self.db, Path(self.tmp.name) / "output")

    def call(self, n, method, path, body=None, version=1):
        login = self.logins[n]
        return self.api.dispatch(method, path, body or {}, login["token"], version, login["csrf"])

    def test_two_authenticated_users_complete_scoped_pipeline(self):
        campaigns = []
        requests = []
        exports = []
        for n in (0, 1):
            self.select(n)
        for n in (0, 1):
            campaign = self.call(n, "POST", "/api/campaigns", {"title": f"Private {n}", "objective": "Explore the product"})
            campaigns.append(campaign)
            plan = self.call(n, "POST", f"/api/campaigns/{campaign['id']}/plan")
            self.call(n, "POST", f"/api/campaigns/{campaign['id']}/approve-plan", {"plan_id": plan["id"]})
            request = self.call(n, "POST", f"/api/campaigns/{campaign['id']}/generate")
            requests.append(request)
            self.assertGreater(len(self.call(n, "GET", f"/api/requests/{request['id']}/preview")), 100)
            with self.assertRaises(PermissionError):
                self.call(1-n, "GET", f"/api/requests/{request['id']}/preview")
            with self.assertRaises(PermissionError):
                self.call(1-n, "POST", f"/api/requests/{request['id']}/review", {"decision": "ACCEPTED", "note": "forged"})
            qa = self.call(n, "POST", f"/api/requests/{request['id']}/qa")
            self.assertEqual(qa["qa"]["overall_result"], "PASS")
            self.assertEqual(qa["gate"]["result"], "PASS")
            self.call(n, "POST", f"/api/requests/{request['id']}/review", {"decision": "ACCEPTED", "note": "Reviewed local MOCK preview"})
            export = self.call(n, "POST", f"/api/requests/{request['id']}/export")
            exports.append(export)
            self.assertGreater(len(self.call(n, "GET", f"/api/exports/{export['id']}/download")), 100)
            detail = self.call(n, "GET", f"/api/campaigns/{campaign['id']}")
            for table in ("generation_queue", "qa_runs", "qa_reviews", "generation_approvals", "generation_spend_ledger"):
                self.assertTrue(detail[table], table)
                for row in detail[table]:
                    with self.assertRaises(PermissionError):
                        self.call(1-n, "GET", f"/api/records/{table}/{row['id']}")
        for n in (0, 1):
            workspace = self.call(n, "GET", "/api/workspace")
            self.assertEqual([c["id"] for c in workspace["campaigns"]], [campaigns[n]["id"]])
            self.assertEqual(workspace["brand"]["name"], self.brands[n]["name"])
            with self.assertRaises(PermissionError):
                self.call(n, "GET", f"/api/campaigns/{campaigns[1-n]['id']}")
            with self.assertRaises(PermissionError):
                self.call(n, "POST", f"/api/requests/{requests[1-n]['id']}/export")
            with self.assertRaises(PermissionError):
                self.call(n, "GET", f"/api/exports/{exports[1-n]['id']}/download")

    def test_forged_ownership_and_stale_context_rejected(self):
        self.select()
        from creativeos_db import CreativeOSStore
        with CreativeOSStore(self.db) as store:
            legacy = store.create("brand_profiles", {"name": "Unowned private"})
            campaign = store.create("campaigns", {"brand_profile_id": legacy["id"], "title": "Unowned"})
        with self.assertRaises(PermissionError):
            self.call(0, "GET", f"/api/campaigns/{campaign['id']}")
        with self.assertRaises(ValueError):
            self.call(0, "POST", "/api/campaigns", {"title": "bad", "organization_id": self.orgs[1]["id"]})
        with self.assertRaises(PermissionError):
            self.call(0, "POST", "/api/campaigns", {"title": "bad"}, version=0)
        self.auth.revoke_membership(self.users[0]["id"], self.orgs[0]["id"])
        with self.assertRaises(PermissionError):
            self.call(0, "GET", "/api/workspace")

    def test_legacy_inaccessible_and_empty_organization_can_adopt(self):
        from creativeos_db import CreativeOSStore
        from creativeos_db.multibrand import MultiBrandService
        with CreativeOSStore(self.db) as store:
            legacy = store.create("brand_profiles", {"name": "Legacy independent"})
            campaign = store.create("campaigns", {"title": "Legacy", "brand_profile_id": legacy["id"]})
            empty = MultiBrandService(store).create_organization("Empty", "empty")
        self.auth.grant_membership(self.users[0]["id"], empty["id"], "OWNER")
        a = self.logins[0]
        self.auth.select_scope(a["token"], a["csrf"], 0, empty["id"], None)
        preview = self.call(0, "POST", "/api/adoption/preview", {"legacy_brand_id": legacy["id"]})
        self.assertEqual(preview["conflicts"], [])
        self.call(0, "POST", "/api/adoption/confirm", {
            "preview_id": preview["id"], "digest": preview["digest"], "confirmation": True})
        self.auth.select_scope(a["token"], a["csrf"], 1, empty["id"], legacy["id"])
        detail = self.call(0, "GET", f"/api/campaigns/{campaign['id']}", version=2)
        self.assertEqual(detail["campaign"]["organization_id"], empty["id"])

    def test_recorded_provider_failure_survives_authorized_request(self):
        from unittest.mock import patch
        from creativeos_db.provider_contract import ProviderError
        self.select()
        campaign = self.call(0, "POST", "/api/campaigns", {"title": "Failure evidence"})
        plan = self.call(0, "POST", f"/api/campaigns/{campaign['id']}/plan")
        self.call(0, "POST", f"/api/campaigns/{campaign['id']}/approve-plan", {"plan_id": plan["id"]})
        with patch("creativeos_db.workflow.LocalPreviewProvider.submit", side_effect=ProviderError("Local test failure", code="TEST_FAILURE")):
            result = self.call(0, "POST", f"/api/campaigns/{campaign['id']}/generate")
        self.assertIn("failure", result)
        detail = self.call(0, "GET", f"/api/campaigns/{campaign['id']}")
        self.assertEqual(detail["generation_attempts"][0]["state"], "FAILED")
        self.assertEqual(detail["generation_attempts"][0]["error_code"], "TEST_FAILURE")
        self.assertEqual(detail["generation_queue"][0]["state"], "FAILED")
        self.assertEqual(detail["export_jobs"], [])

    def test_switching_between_authorized_brands_rejects_old_authority(self):
        from creativeos_db import CreativeOSStore
        from creativeos_db.multibrand import MultiBrandService
        self.select()
        campaign = self.call(0, "POST", "/api/campaigns", {"title": "First brand only"})
        with CreativeOSStore(self.db) as store:
            other = MultiBrandService(store).create_brand(self.orgs[0]["id"], {"name": "Independent product"})
        a = self.logins[0]
        self.auth.select_scope(a["token"], a["csrf"], 1, self.orgs[0]["id"], other["id"])
        self.assertEqual(self.call(0, "GET", "/api/workspace", version=2)["campaigns"], [])
        for method, path in (
            ("GET", f"/api/campaigns/{campaign['id']}"),
            ("POST", f"/api/campaigns/{campaign['id']}/plan"),
            ("POST", f"/api/campaigns/{campaign['id']}/generate"),
        ):
            with self.assertRaises(PermissionError):
                self.call(0, method, path, version=2)
        with self.assertRaises(PermissionError):
            self.call(0, "POST", "/api/campaigns", {"title": "stale tab"}, version=1)

    def test_legacy_identifiers_cannot_become_filesystem_paths(self):
        from types import SimpleNamespace
        from creativeos_db.workflow import CampaignWorkflow
        root = Path(self.tmp.name) / "output"
        contexts = [
            SimpleNamespace(organization_id="../../outside", brand_profile_id="../other", store=None),
            SimpleNamespace(organization_id="normal", brand_profile_id="normal", store=None),
        ]
        paths = [CampaignWorkflow(ctx, root).root for ctx in contexts]
        self.assertNotEqual(paths[0], paths[1])
        for path in paths:
            self.assertEqual(len(path.relative_to(root.resolve()).parts), 2)
            self.assertTrue(all(len(part) == 64 for part in path.relative_to(root.resolve()).parts))


if __name__ == "__main__":
    unittest.main()
