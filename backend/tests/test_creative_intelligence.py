import sqlite3
import tempfile
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.creative_intelligence import (
    CreativeIntelligenceService,
    ProviderCapabilityRegistry,
)
from creativeos_db.creative_intelligence_api import ApplicationAPI
from creativeos_db.migrations import MIGRATIONS
from creativeos_db.multibrand import MultiBrandService
from test_authenticated_scope import AuthFixture


class CreativeIntelligenceFoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "creative-intelligence.sqlite3"
        with CreativeOSStore(self.db) as store:
            self.assertEqual(store.migrate_to_latest(), 13)
            multi = MultiBrandService(store)
            self.org_a = multi.create_organization("Alpha", "alpha-ci")
            self.org_b = multi.create_organization("Beta", "beta-ci")
            self.brand_a = multi.create_brand(self.org_a["id"], {"name": "Alpha Main"})
            self.brand_a2 = multi.create_brand(self.org_a["id"], {"name": "Alpha Second"})
            self.brand_b = multi.create_brand(self.org_b["id"], {"name": "Beta Main"})

    def tearDown(self):
        self.tmp.cleanup()

    def scoped(self, org, brand):
        return CreativeOSStore(
            self.db, organization_id=org["id"], brand_profile_id=brand["id"],
        )

    def test_v12_v13_upgrade_rollback_reapply_and_asset_backward_compatibility(self):
        legacy = Path(self.tmp.name) / "legacy.sqlite3"
        with CreativeOSStore(legacy) as store:
            for version in range(1, 13):
                store._migration_script(MIGRATIONS[version][0])
            brand = store.create("brand_profiles", {"name": "Legacy Brand"})
            campaign = store.create(
                "campaigns", {"brand_profile_id": brand["id"], "title": "Legacy campaign"},
            )
            asset = store.create(
                "assets",
                {
                    "campaign_id": campaign["id"],
                    "asset_type": "photo",
                    "path": "legacy.jpg",
                    "source": "upload",
                },
            )
            before_source = asset["source"]
            self.assertEqual(store.schema_version(), 12)
            self.assertEqual(store.migrate_to_latest(), 13)
            migrated = store.get("assets", asset["id"])
            self.assertEqual(migrated["source"], before_source)
            self.assertIsNone(migrated["truth_level"])
            self.assertEqual(migrated["reference_fidelity_required"], 0)
            self.assertEqual(store.rollback_to(12), 12)
            self.assertEqual(store.migrate_to_latest(), 13)
            self.assertEqual(store.foreign_key_violations(), [])

    def test_crud_relationships_evidence_reference_and_guardrails(self):
        with self.scoped(self.org_a, self.brand_a) as store:
            service = CreativeIntelligenceService(store)
            market = service.create_market_intelligence({
                "subject": "Kitchen design service",
                "subject_type": "SERVICE",
                "intelligence_type": "PAIN_POINT",
                "evidence_source": "Qualified sales calls",
                "notes": "Clients hesitate when scope is visually unclear.",
            })
            market = service.update_market_intelligence(
                market["id"], {"notes": "Clients ask for visual certainty before fabrication."},
            )
            self.assertIn("visual certainty", market["notes"])

            hypothesis = service.create_hypothesis({
                "objective": "Increase qualified design inquiries",
                "audience": "Renovating homeowners",
                "pain_point": "Uncertainty before construction",
                "offer": "Paid design consultation",
                "angle": "Design before you build",
                "hook": "See the kitchen before fabrication",
                "proof": "Approved project render and completed-work evidence",
                "cta": "Book a design session",
                "format": "9:16 video",
                "funnel_stage": "CONSIDERATION",
                "platform": "META",
                "success_metric": "Qualified paid design bookings",
                "evidence_state": "LIMITED",
                "unresolved_assumptions": "Need enough observations across campaigns.",
            })
            with self.assertRaisesRegex(ValueError, "unsupported fields"):
                service.update_hypothesis(hypothesis["id"], {"conversion_probability": 0.92})

            evidence = service.add_evidence({
                "hypothesis_id": hypothesis["id"],
                "market_intelligence_id": market["id"],
                "source": "Sales log",
                "observation": "Three recent prospects requested a design preview first.",
                "sample_size": 3,
                "evidence_strength": "LIMITED",
            })
            self.assertEqual(evidence["sample_size"], 3)
            self.assertEqual(
                service.get_hypothesis(hypothesis["id"])["evidence"][0]["observation"],
                evidence["observation"],
            )

            reference = service.create_reference_pattern({
                "reference_source": "Approved real-project ad",
                "hook_pattern": "Problem then visual certainty",
                "offer_pattern": "Low-friction paid design",
                "composition_pattern": "Real room to approved render",
                "proof_mechanism": "Completed project photography",
                "cta_pattern": "Book design",
                "format": "9:16",
                "audience_stage": "CONSIDERATION",
                "brand_safe_adaptation_notes": "Use only verified JB project claims.",
            })
            self.assertEqual(
                service.list_reference_patterns()[0]["id"], reference["id"],
            )

            experiment = service.create_experiment({
                "hypothesis_id": hypothesis["id"],
                "variant": "A — real project first",
                "campaign_external_id": "meta-campaign-known-later",
                "status": "READY",
            })
            self.assertEqual(experiment["hypothesis_id"], hypothesis["id"])

            campaign = store.create("campaigns", {
                "organization_id": self.org_a["id"],
                "brand_profile_id": self.brand_a["id"],
                "title": "Existing production campaign",
            })
            asset = store.create("assets", {
                "campaign_id": campaign["id"],
                "asset_type": "photo",
                "path": "verified-kitchen.jpg",
                "source": "upload",
            })
            link = service.link_experiment_asset(experiment["id"], asset["id"])
            self.assertEqual(link["asset_id"], asset["id"])
            self.assertEqual(
                service.list_experiment_assets(experiment["id"])[0]["id"], link["id"],
            )

            provenance = service.set_asset_provenance(
                asset["id"], truth_level="REAL_PROJECT", reference_fidelity_required=True,
            )
            self.assertEqual(provenance["source"], "upload")
            self.assertEqual(provenance["truth_level"], "REAL_PROJECT")
            self.assertEqual(provenance["reference_fidelity_required"], 1)

            overview = service.overview()
            self.assertEqual(len(overview["market_intelligence"]), 1)
            self.assertEqual(len(overview["hypotheses"]), 1)
            self.assertEqual(len(overview["reference_patterns"]), 1)
            self.assertEqual(len(overview["experiments"]), 1)

    def test_tenant_and_brand_isolation_and_cross_scope_links_are_denied(self):
        with self.scoped(self.org_a, self.brand_a) as store_a:
            service_a = CreativeIntelligenceService(store_a)
            hypothesis = service_a.create_hypothesis({"objective": "Alpha only"})
            experiment = service_a.create_experiment({
                "hypothesis_id": hypothesis["id"], "variant": "Alpha variant",
            })
            campaign = store_a.create("campaigns", {
                "organization_id": self.org_a["id"],
                "brand_profile_id": self.brand_a["id"],
                "title": "Alpha assets",
            })
            alpha_asset = store_a.create("assets", {
                "campaign_id": campaign["id"], "asset_type": "photo", "path": "alpha.jpg",
            })

        with self.scoped(self.org_a, self.brand_a2) as same_org_other_brand:
            other_brand_service = CreativeIntelligenceService(same_org_other_brand)
            self.assertEqual(other_brand_service.list_hypotheses(), [])
            with self.assertRaises(KeyError):
                other_brand_service.update_hypothesis(hypothesis["id"], {"hook": "forged"})

        with self.scoped(self.org_b, self.brand_b) as store_b:
            service_b = CreativeIntelligenceService(store_b)
            self.assertEqual(service_b.list_hypotheses(), [])
            campaign_b = store_b.create("campaigns", {
                "organization_id": self.org_b["id"],
                "brand_profile_id": self.brand_b["id"],
                "title": "Beta assets",
            })
            beta_asset = store_b.create("assets", {
                "campaign_id": campaign_b["id"], "asset_type": "photo", "path": "beta.jpg",
            })

        with self.scoped(self.org_a, self.brand_a) as store_a:
            service_a = CreativeIntelligenceService(store_a)
            with self.assertRaises(PermissionError):
                service_a.link_experiment_asset(experiment["id"], beta_asset["id"])
            self.assertEqual(
                service_a.list_experiment_assets(experiment["id"])[0:]
                if service_a.list_experiment_assets(experiment["id"]) else [],
                [],
            )
            self.assertEqual(store_a.get("assets", alpha_asset["id"])["path"], "alpha.jpg")

    def test_provider_capability_registry_persists_without_enabling_calls(self):
        with CreativeOSStore(self.db) as store:
            registry = ProviderCapabilityRegistry(store)
            item = registry.upsert({
                "provider": "HIGGSFIELD",
                "model": "reference-video",
                "supported_job_types": ["video", "reference-video"],
                "estimated_cost_metadata": {"currency": "USD", "source": "operator-configured"},
                "reference_fidelity_capability": "HIGH",
                "enabled": False,
            })
            self.assertFalse(item["enabled"])
            self.assertEqual(item["reference_fidelity_capability"], "HIGH")
        with CreativeOSStore(self.db) as reopened:
            rows = ProviderCapabilityRegistry(reopened).list()
            self.assertEqual(rows[0]["model"], "reference-video")
            with self.scoped(self.org_a, self.brand_a) as scoped:
                with self.assertRaises(PermissionError):
                    ProviderCapabilityRegistry(scoped)

    def test_v13_rollback_refuses_to_discard_intelligence_or_provenance(self):
        with self.scoped(self.org_a, self.brand_a) as scoped:
            CreativeIntelligenceService(scoped).create_hypothesis({"objective": "Keep evidence"})
        with CreativeOSStore(self.db) as store:
            with self.assertRaises(sqlite3.IntegrityError):
                store.rollback_to(12)
            self.assertEqual(store.schema_version(), 13)
            self.assertEqual(store.foreign_key_violations(), [])


class CreativeIntelligenceAPITests(AuthFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.api = ApplicationAPI(self.db, Path(self.tmp.name) / "output")

    def call(self, n, method, path, body=None, version=1, csrf=None):
        login = self.logins[n]
        return self.api.dispatch(
            method, path, body or {}, login["token"], version,
            login["csrf"] if csrf is None else csrf,
        )

    def test_authenticated_api_scopes_reads_writes_and_evidence(self):
        self.select(0)
        self.select(1)
        hypothesis = self.call(0, "POST", "/api/intelligence/hypotheses", {
            "objective": "Alice private hypothesis",
            "evidence_state": "INSUFFICIENT",
        })
        evidence = self.call(
            0, "POST", f"/api/intelligence/hypotheses/{hypothesis['id']}/evidence",
            {
                "source": "Owned observation",
                "observation": "One verified customer observation.",
                "sample_size": 1,
                "evidence_strength": "LIMITED",
            },
        )
        self.assertEqual(evidence["sample_size"], 1)
        overview_a = self.call(0, "GET", "/api/intelligence")
        overview_b = self.call(1, "GET", "/api/intelligence")
        self.assertEqual(overview_a["hypotheses"][0]["id"], hypothesis["id"])
        self.assertEqual(overview_b["hypotheses"], [])
        with self.assertRaises(KeyError):
            self.call(
                1, "POST", f"/api/intelligence/hypotheses/{hypothesis['id']}",
                {"hook": "forged cross-tenant update"},
            )
        with self.assertRaises(PermissionError):
            self.call(
                0, "POST", "/api/intelligence/hypotheses",
                {"objective": "forged csrf"}, csrf="forged",
            )
        with self.assertRaises(PermissionError):
            self.call(
                0, "POST", "/api/intelligence/hypotheses",
                {"objective": "stale scope"}, version=0,
            )


if __name__ == "__main__":
    unittest.main()
