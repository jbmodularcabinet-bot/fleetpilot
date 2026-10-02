import tempfile
import unittest
from pathlib import Path

from creativeos_db import CreativeOSStore
from creativeos_db.generation_engine import BudgetGuard, GenerationOrchestrator
from creativeos_db.multibrand import MultiBrandService


class MultiBrandFoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "creativeos.sqlite3"
        self.store = CreativeOSStore(self.db)
        self.assertEqual(self.store.migrate_to_latest(), 13)
        self.multi = MultiBrandService(self.store)
        self.habi = self.multi.create_organization(
            "HABI Group",
            "habi-group",
            classification="NATIVE",
            ecosystem_key="habi",
            organization_id="org-habi",
        )
        self.external = self.multi.create_organization(
            "Northstar Labs",
            "northstar-labs",
            organization_id="org-northstar",
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()
    def _brand(
        self,
        organization_id: str,
        brand_id: str,
        name: str,
        *,
        entity_type: str = "BRAND",
    ):
        return self.multi.create_brand(
            organization_id,
            {
                "id": brand_id,
                "name": name,
                "display_name": name,
                "core_promise": f"{name} approved promise",
                "messaging_json": [f"{name} approved message"],
            },
            entity_type=entity_type,
        )

    def _campaign_stack(
        self,
        organization_id: str,
        brand_id: str,
        prefix: str,
    ):
        campaign = self.multi.create_campaign(
            organization_id,
            brand_id,
            {"id": f"{prefix}-campaign", "title": f"{prefix} Campaign"},
        )
        board = self.store.create(
            "storyboards",
            {"id": f"{prefix}-board", "campaign_id": campaign["id"], "title": "Board"},
        )
        scene = self.store.create(
            "scenes",
            {
                "id": f"{prefix}-scene",
                "storyboard_id": board["id"],
                "position": 1,
                "title": "Scene",
                "scene_type": "GENERATED",
                "immutable_ui": 0,
            },
        )
        requirement = self.store.create(
            "asset_requirements",
            {
                "id": f"{prefix}-req",
                "scene_id": scene["id"],
                "asset_type": "image",
                "purpose": "hero",
                "description": "scoped asset",
            },
        )
        asset = self.store.create(
            "assets",
            {
                "id": f"{prefix}-asset",
                "campaign_id": campaign["id"],
                "asset_type": "image",
                "path": f"C:\\CreativeOS\\{prefix}.png",
            },
        )
        job = self.store.create(
            "generation_jobs",
            {
                "id": f"{prefix}-job",
                "scene_id": scene["id"],
                "provider": "MOCK",
                "model": "image",
                "asset_requirement_id": requirement["id"],
            },
        )
        generated = self.store.create(
            "generated_assets",
            {
                "id": f"{prefix}-generated",
                "generation_job_id": job["id"],
                "asset_requirement_id": requirement["id"],
                "output_path": f"C:\\CreativeOS\\{prefix}-generated.png",
                "output_type": "image",
                "prompt_snapshot": "scoped",
                "provider_snapshot": "MOCK",
                "model_snapshot": "image",
                "checksum_sha256": prefix.ljust(64, "0")[:64],
            },
        )
        cost = self.store.create(
            "cost_recommendations",
            {
                "id": f"{prefix}-cost",
                "asset_requirement_id": requirement["id"],
                "campaign_id": campaign["id"],
            },
        )
        request = GenerationOrchestrator(self.store).create_request(
            asset_requirement_id=requirement["id"],
            tenant_id=organization_id,
            user_id=f"{prefix}-owner",
            idempotency_key=f"{prefix}-idem",
            intent="STATIC_META",
            original_prompt=f"Create {prefix} campaign artwork",
        )
        policy = BudgetGuard(self.store).set_policy(
            organization_id,
            campaign["id"],
            campaign_limit_minor=10_000,
            tenant_daily_limit_minor=20_000,
            approval_required_minor=5_000,
        )
        spend = self.store.create(
            "generation_spend_ledger",
            {
                "id": f"{prefix}-spend",
                "request_id": request["id"],
                "tenant_id": organization_id,
                "campaign_id": campaign["id"],
                "event_type": "RESERVED",
                "amount_minor": 100,
                "currency": "USD",
                "spend_date": "2026-09-30",
            },
        )
        attempt = self.store.create(
            "generation_attempts",
            {
                "id": f"{prefix}-attempt",
                "request_id": request["id"],
                "attempt_number": 1,
                "provider": "MOCK",
                "model": "image",
                "state": "SUCCEEDED",
                "provider_request_id": f"{prefix}-provider",
                "correlation_id": f"{prefix}-correlation",
                "compiled_prompt": request["compiled_prompt"],
                "settings_json": {},
                "references_json": [],
                "estimated_cost_minor": 100,
                "actual_cost_minor": 100,
                "actual_cost_source": "MOCK",
                "currency": "USD",
                "currency_minor_exponent": 4,
            },
        )
        result = self.store.create(
            "generation_results",
            {
                "id": f"{prefix}-result",
                "request_id": request["id"],
                "attempt_id": attempt["id"],
                "provider_request_id": f"{prefix}-provider",
                "output_url": f"https://example.invalid/{prefix}.png",
                "local_path": f"C:\\CreativeOS\\{prefix}-result.png",
                "output_type": "image",
                "output_metadata_json": {},
                "checksum_sha256": (prefix + "r").ljust(64, "0")[:64],
                "estimated_cost_minor": 100,
                "actual_cost_minor": 100,
                "actual_cost_source": "MOCK",
                "currency": "USD",
                "currency_minor_exponent": 4,
            },
        )
        provenance = self.store.create(
            "generation_provenance",
            {
                "id": f"{prefix}-provenance",
                "result_id": result["id"],
                "request_id": request["id"],
                "tenant_id": organization_id,
                "user_id": f"{prefix}-owner",
                "campaign_id": campaign["id"],
                "brand_profile_id": brand_id,
                "original_prompt": request["original_prompt"],
                "compiled_provider_prompt": request["compiled_prompt"],
                "provider": "MOCK",
                "model": "image",
                "settings_json": {},
                "references_json": [],
                "estimated_cost_minor": 100,
                "actual_cost_minor": 100,
                "actual_cost_source": "MOCK",
                "currency": "USD",
                "currency_minor_exponent": 4,
                "provider_request_id": f"{prefix}-provider",
            },
        )
        approval = self.store.create(
            "generation_approvals",
            {
                "id": f"{prefix}-approval",
                "request_id": request["id"],
                "approval_type": "BUDGET",
                "decision": "APPROVED",
                "approved_by": f"{prefix}-owner",
                "note": "scoped proof",
            },
        )
        export = self.store.create(
            "export_jobs",
            {
                "id": f"{prefix}-export",
                "campaign_id": campaign["id"],
                "preset": "16:9",
            },
        )
        return {
            "campaign": campaign,
            "board": board,
            "scene": scene,
            "requirement": requirement,
            "asset": asset,
            "generated": generated,
            "cost": cost,
            "request": request,
            "policy": policy,
            "spend": spend,
            "provenance": provenance,
            "approval": approval,
            "export": export,
        }
    def test_native_organization_can_hold_multiple_products(self):
        fleet = self._brand(
            self.habi["id"], "brand-fleet", "FleetPilot", entity_type="PRODUCT"
        )
        aesthetic = self._brand(
            self.habi["id"], "brand-aesthetic", "Aesthetic OS", entity_type="PRODUCT"
        )
        self.assertEqual(fleet["organization_id"], self.habi["id"])
        self.assertEqual(aesthetic["organization_id"], self.habi["id"])
        self.assertEqual(fleet["entity_type"], "PRODUCT")
        self.assertEqual(self.habi["classification"], "NATIVE")
        self.assertEqual(self.habi["ecosystem_key"], "habi")

    def test_external_brand_inherits_no_native_branding(self):
        external = self._brand(
            self.external["id"], "brand-client", "Client Cloud"
        )
        self.assertEqual(external["organization_id"], self.external["id"])
        self.assertEqual(external["palette_json"], [])
        self.assertEqual(external["fonts_json"], [])
        self.assertEqual(external["tagline"], "")
        self.assertNotIn("habi", str(external).lower())

    def test_same_brand_name_isolated_by_organization(self):
        self._brand(self.habi["id"], "brand-shared-a", "Shared Name")
        self._brand(self.external["id"], "brand-shared-b", "Shared Name")
        with self.assertRaises(Exception):
            self._brand(self.habi["id"], "brand-shared-c", "Shared Name")
        with self.assertRaises(Exception):
            self.store.rollback_to(10)
        self.assertEqual(self.store.schema_version(), 13)
        self.assertIn("organization_id", self.store._columns("brand_profiles"))

    def test_campaign_resolves_only_its_brand_brain(self):
        brand_a = self._brand(self.habi["id"], "brand-a", "Alpha")
        brand_b = self._brand(self.external["id"], "brand-b", "Beta")
        campaign = self.multi.create_campaign(
            self.habi["id"],
            brand_a["id"],
            {"id": "campaign-a", "title": "Alpha Launch"},
        )
        resolved = self.multi.resolve_campaign_brand(
            self.habi["id"], campaign["id"]
        )
        self.assertEqual(resolved["id"], brand_a["id"])
        self.assertNotEqual(resolved["id"], brand_b["id"])
        with self.assertRaises(PermissionError):
            self.multi.resolve_campaign_brand(
                self.external["id"], campaign["id"]
            )

    def test_database_rejects_cross_organization_campaign_link(self):
        brand = self._brand(self.habi["id"], "brand-native", "Native Product")
        with self.assertRaises(Exception):
            self.store.create(
                "campaigns",
                {
                    "id": "bad-campaign",
                    "organization_id": self.external["id"],
                    "brand_profile_id": brand["id"],
                    "title": "Invalid",
                },
            )
        self.multi.create_campaign(
            self.habi["id"],
            brand["id"],
            {"id": "valid-campaign", "title": "Valid"},
        )
        with self.assertRaises(Exception):
            self.store.update(
                "brand_profiles",
                brand["id"],
                {"organization_id": self.external["id"]},
            )

    def test_assets_costs_and_governance_are_brand_scoped(self):
        brand_a = self._brand(self.habi["id"], "brand-scope-a", "Scope A")
        brand_b = self._brand(
            self.external["id"], "brand-scope-b", "Scope B"
        )
        stack_a = self._campaign_stack(
            self.habi["id"], brand_a["id"], "scope-a"
        )
        stack_b = self._campaign_stack(
            self.external["id"], brand_b["id"], "scope-b"
        )

        assets_a = self.multi.list_brand_assets(
            self.habi["id"], brand_a["id"]
        )
        self.assertEqual(
            {row["id"] for row in assets_a["assets"]},
            {stack_a["asset"]["id"]},
        )
        self.assertEqual(
            {row["id"] for row in assets_a["generated_assets"]},
            {stack_a["generated"]["id"]},
        )

        costs_a = self.multi.list_brand_costs(
            self.habi["id"], brand_a["id"]
        )
        self.assertEqual(
            {row["id"] for row in costs_a["recommendations"]},
            {stack_a["cost"]["id"]},
        )
        self.assertEqual(
            {row["id"] for row in costs_a["generation_budget_policies"]},
            {stack_a["policy"]["id"]},
        )
        self.assertEqual(
            {row["id"] for row in costs_a["generation_spend_ledger"]},
            {stack_a["spend"]["id"]},
        )
        self.assertNotIn(
            stack_b["spend"]["id"],
            {row["id"] for row in costs_a["generation_spend_ledger"]},
        )
        governance_a = self.multi.list_brand_governance(
            self.habi["id"], brand_a["id"]
        )
        self.assertEqual(
            {row["id"] for row in governance_a["generation_requests"]},
            {stack_a["request"]["id"]},
        )
        self.assertEqual(
            {row["id"] for row in governance_a["generation_approvals"]},
            {stack_a["approval"]["id"]},
        )
        self.assertEqual(
            {row["id"] for row in governance_a["generation_provenance"]},
            {stack_a["provenance"]["id"]},
        )
        self.assertNotIn(
            stack_b["provenance"]["id"],
            {row["id"] for row in governance_a["generation_provenance"]},
        )
        self.assertEqual(
            {row["id"] for row in governance_a["export_jobs"]},
            {stack_a["export"]["id"]},
        )
        self.assertNotIn(
            stack_b["request"]["id"],
            {row["id"] for row in governance_a["generation_requests"]},
        )

    def test_generation_and_budget_reject_cross_tenant_access(self):
        brand = self._brand(self.habi["id"], "brand-gen", "Generation Brand")
        stack = self._campaign_stack(
            self.habi["id"], brand["id"], "generation-scope"
        )
        with self.assertRaises(PermissionError):
            GenerationOrchestrator(self.store).create_request(
                asset_requirement_id=stack["requirement"]["id"],
                tenant_id=self.external["id"],
                user_id="outsider",
                idempotency_key="cross-tenant",
                intent="STATIC_META",
                original_prompt="wrong tenant",
            )
        with self.assertRaises(PermissionError):
            BudgetGuard(self.store).set_policy(
                self.external["id"],
                stack["campaign"]["id"],
                campaign_limit_minor=1000,
                tenant_daily_limit_minor=1000,
                approval_required_minor=500,
            )

    def test_v10_v11_legacy_compatibility(self):
        other = Path(self.tmp.name) / "legacy.sqlite3"
        store = CreativeOSStore(other)
        self.assertEqual(store.migrate_to_latest(), 13)
        self.assertEqual(store.rollback_to(10), 10)
        legacy_brand = store.create(
            "brand_profiles", {"id": "legacy-brand", "name": "Legacy"}
        )
        legacy_campaign = store.create(
            "campaigns",
            {
                "id": "legacy-campaign",
                "brand_profile_id": legacy_brand["id"],
                "title": "Legacy Campaign",
            },
        )
        self.assertEqual(store.migrate_to_latest(), 13)
        migrated_brand = store.get("brand_profiles", legacy_brand["id"])
        migrated_campaign = store.get("campaigns", legacy_campaign["id"])
        self.assertIsNone(migrated_brand["organization_id"])
        self.assertIsNone(migrated_campaign["organization_id"])
        self.assertEqual(store.rollback_to(10), 10)
        self.assertEqual(store.get("brand_profiles", legacy_brand["id"])["name"], "Legacy")
        self.assertEqual(store.migrate_to_latest(), 13)
        self.assertEqual(store.foreign_key_violations(), [])
        store.close()


if __name__ == "__main__":
    unittest.main()
