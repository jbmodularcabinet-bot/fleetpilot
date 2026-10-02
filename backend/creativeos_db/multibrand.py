from __future__ import annotations

import re
from typing import Any

from .brand_service import BrandBrainService
from .store import CreativeOSStore


_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ORG_CLASSES = {"NATIVE", "EXTERNAL"}
_ENTITY_TYPES = {"BRAND", "PRODUCT"}


class MultiBrandService:
    """Organization/brand boundary for new multi-brand CreativeOS data."""

    def __init__(self, store: CreativeOSStore):
        self.store = store
        self.brands = BrandBrainService(store)

    def create_organization(
        self,
        name: str,
        slug: str,
        *,
        classification: str = "EXTERNAL",
        ecosystem_key: str = "",
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        name = str(name or "").strip()
        slug = str(slug or "").strip().lower()
        classification = str(classification or "").upper().strip()
        ecosystem_key = str(ecosystem_key or "").strip().lower()
        if not name:
            raise ValueError("organization name is required")
        if not _SLUG.fullmatch(slug):
            raise ValueError("organization slug must use lowercase letters, numbers, and hyphens")
        if classification not in _ORG_CLASSES:
            raise ValueError("classification must be NATIVE or EXTERNAL")
        values: dict[str, Any] = {
            "name": name,
            "slug": slug,
            "classification": classification,
            "ecosystem_key": ecosystem_key,
        }
        if organization_id:
            values["id"] = organization_id
        return self.store.create("organizations", values)

    def get_organization(self, organization_id: str) -> dict[str, Any]:
        return self.store.get("organizations", organization_id)

    def create_brand(
        self,
        organization_id: str,
        values: dict[str, Any],
        *,
        entity_type: str = "BRAND",
    ) -> dict[str, Any]:
        self.get_organization(organization_id)
        entity_type = str(entity_type or "").upper().strip()
        if entity_type not in _ENTITY_TYPES:
            raise ValueError("entity_type must be BRAND or PRODUCT")
        payload = dict(values)
        payload["organization_id"] = organization_id
        payload["entity_type"] = entity_type
        return self.brands.create(payload)

    def get_brand(
        self, organization_id: str, brand_profile_id: str
    ) -> dict[str, Any]:
        brand = self.brands.get(brand_profile_id)
        if brand.get("organization_id") != organization_id:
            raise PermissionError("brand does not belong to organization")
        return brand

    def create_campaign(
        self,
        organization_id: str,
        brand_profile_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        self.get_brand(organization_id, brand_profile_id)
        payload = dict(values)
        payload["organization_id"] = organization_id
        payload["brand_profile_id"] = brand_profile_id
        return self.store.create("campaigns", payload)

    def resolve_campaign_brand(
        self, organization_id: str, campaign_id: str
    ) -> dict[str, Any]:
        campaign = self.store.get("campaigns", campaign_id)
        if campaign.get("organization_id") != organization_id:
            raise PermissionError("campaign does not belong to organization")
        return self.get_brand(organization_id, campaign["brand_profile_id"])

    def assert_campaign_scope(
        self,
        organization_id: str,
        brand_profile_id: str,
        campaign_id: str,
    ) -> dict[str, Any]:
        campaign = self.store.get("campaigns", campaign_id)
        if (
            campaign.get("organization_id") != organization_id
            or campaign.get("brand_profile_id") != brand_profile_id
        ):
            raise PermissionError("campaign is outside requested brand scope")
        self.get_brand(organization_id, brand_profile_id)
        return campaign

    def list_campaigns(
        self, organization_id: str, brand_profile_id: str | None = None
    ) -> list[dict[str, Any]]:
        self.get_organization(organization_id)
        filters: dict[str, Any] = {"organization_id": organization_id}
        if brand_profile_id is not None:
            self.get_brand(organization_id, brand_profile_id)
            filters["brand_profile_id"] = brand_profile_id
        return self.store.list("campaigns", filters)

    def _scope_ids(
        self,
        view: str,
        id_column: str,
        organization_id: str,
        brand_profile_id: str,
    ) -> list[str]:
        self.get_brand(organization_id, brand_profile_id)
        rows = self.store.conn.execute(
            f"""SELECT {id_column} FROM {view}
                WHERE organization_id=? AND brand_profile_id=?
                ORDER BY {id_column}""",
            (organization_id, brand_profile_id),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def list_brand_assets(
        self, organization_id: str, brand_profile_id: str
    ) -> dict[str, list[dict[str, Any]]]:
        asset_ids = self._scope_ids(
            "v_asset_scope", "asset_id", organization_id, brand_profile_id
        )
        generated_ids = self._scope_ids(
            "v_generated_asset_scope",
            "generated_asset_id",
            organization_id,
            brand_profile_id,
        )
        return {
            "assets": [self.store.get("assets", row_id) for row_id in asset_ids],
            "generated_assets": [
                self.store.get("generated_assets", row_id)
                for row_id in generated_ids
            ],
        }

    def list_brand_costs(
        self, organization_id: str, brand_profile_id: str
    ) -> dict[str, list[dict[str, Any]]]:
        recommendation_ids = self._scope_ids(
            "v_cost_recommendation_scope",
            "cost_recommendation_id",
            organization_id,
            brand_profile_id,
        )
        recommendations = [
            self.store.get("cost_recommendations", row_id)
            for row_id in recommendation_ids
        ]
        estimates: list[dict[str, Any]] = []
        overrides: list[dict[str, Any]] = []
        for recommendation_id in recommendation_ids:
            estimates.extend(
                self.store.list(
                    "cost_estimates", {"recommendation_id": recommendation_id}
                )
            )
            overrides.extend(
                self.store.list(
                    "cost_overrides", {"recommendation_id": recommendation_id}
                )
            )
        campaign_ids = self._scope_ids(
            "v_campaign_scope",
            "campaign_id",
            organization_id,
            brand_profile_id,
        )
        budget_policies: list[dict[str, Any]] = []
        spend_ledger: list[dict[str, Any]] = []
        for campaign_id in campaign_ids:
            budget_policies.extend(
                self.store.list(
                    "generation_budget_policies",
                    {"tenant_id": organization_id, "campaign_id": campaign_id},
                )
            )
            spend_ledger.extend(
                self.store.list(
                    "generation_spend_ledger",
                    {"tenant_id": organization_id, "campaign_id": campaign_id},
                )
            )
        return {
            "recommendations": recommendations,
            "estimates": estimates,
            "overrides": overrides,
            "generation_budget_policies": budget_policies,
            "generation_spend_ledger": spend_ledger,
        }

    def list_brand_governance(
        self, organization_id: str, brand_profile_id: str
    ) -> dict[str, list[dict[str, Any]]]:
        self.get_brand(organization_id, brand_profile_id)
        requests = self.store.list(
            "generation_requests",
            {"tenant_id": organization_id, "brand_profile_id": brand_profile_id},
        )
        approvals: list[dict[str, Any]] = []
        gate_runs: list[dict[str, Any]] = []
        for request in requests:
            approvals.extend(
                self.store.list(
                    "generation_approvals", {"request_id": request["id"]}
                )
            )
            gate_runs.extend(
                self.store.list(
                    "generation_gate_runs", {"request_id": request["id"]}
                )
            )
        provenance = self.store.list(
            "generation_provenance",
            {"tenant_id": organization_id, "brand_profile_id": brand_profile_id},
        )
        qa_review_ids = self._scope_ids(
            "v_qa_review_scope",
            "qa_review_id",
            organization_id,
            brand_profile_id,
        )
        export_ids = self._scope_ids(
            "v_export_scope",
            "export_job_id",
            organization_id,
            brand_profile_id,
        )
        return {
            "generation_requests": requests,
            "generation_approvals": approvals,
            "generation_gate_runs": gate_runs,
            "generation_provenance": provenance,
            "qa_reviews": [
                self.store.get("qa_reviews", row_id) for row_id in qa_review_ids
            ],
            "export_jobs": [
                self.store.get("export_jobs", row_id) for row_id in export_ids
            ],
        }
