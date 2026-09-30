"""Frozen ownership graph for schema v11; migrations must not depend on runtime state."""

# First relationship owns the row. Additional relationships must share its scope.
PARENTS = {
    "creative_memory": [("brand_profile_id", "brand_profiles")],
    "storyboards": [("campaign_id", "campaigns")],
    "director_plans": [("campaign_id", "campaigns")],
    "scenes": [("storyboard_id", "storyboards"), ("selected_version_id", "scene_versions"),
               ("approved_version_id", "scene_versions")],
    "scene_versions": [("scene_id", "scenes")],
    "asset_requirements": [("scene_id", "scenes")],
    "generation_jobs": [("scene_id", "scenes"), ("asset_requirement_id", "asset_requirements"),
                        ("retry_of_id", "generation_jobs")],
    "generated_assets": [("asset_requirement_id", "asset_requirements"), ("generation_job_id", "generation_jobs")],
    "generation_queue": [("generation_job_id", "generation_jobs")],
    "qa_results": [("campaign_id", "campaigns"), ("scene_id", "scenes")],
    "export_jobs": [("campaign_id", "campaigns")],
    "cost_recommendations": [("campaign_id", "campaigns"), ("asset_requirement_id", "asset_requirements")],
    "cost_estimates": [("recommendation_id", "cost_recommendations")],
    "cost_overrides": [("recommendation_id", "cost_recommendations"), ("selected_estimate_id", "cost_estimates"),
                       ("original_recommended_estimate_id", "cost_estimates")],
    "voice_jobs": [("scene_id", "scenes"), ("generation_job_id", "generation_jobs")],
    "composition_timelines": [("campaign_id", "campaigns"), ("storyboard_id", "storyboards")],
    "composition_timeline_entries": [("timeline_id", "composition_timelines"), ("scene_id", "scenes"),
                                     ("scene_version_id", "scene_versions"), ("generated_asset_id", "generated_assets")],
    "render_jobs": [("timeline_id", "composition_timelines")],
    "render_attempts": [("render_job_id", "render_jobs")],
    "qa_runs": [("render_job_id", "render_jobs"), ("retry_of_qa_run_id", "qa_runs")],
    "qa_check_results": [("qa_run_id", "qa_runs")],
    "qa_reviews": [("qa_run_id", "qa_runs")],
    "generation_requests": [("campaign_id", "campaigns"), ("brand_profile_id", "brand_profiles"),
                            ("asset_requirement_id", "asset_requirements"), ("generation_job_id", "generation_jobs"),
                            ("parent_asset_id", "assets")],
    "generation_lifecycle_events": [("request_id", "generation_requests")],
    "generation_attempts": [("request_id", "generation_requests")],
    "generation_results": [("request_id", "generation_requests"), ("attempt_id", "generation_attempts")],
    "generation_provenance": [("request_id", "generation_requests"), ("result_id", "generation_results"),
                              ("campaign_id", "campaigns"), ("brand_profile_id", "brand_profiles"),
                              ("parent_asset_id", "assets")],
    "generation_budget_policies": [("campaign_id", "campaigns")],
    "generation_spend_ledger": [("request_id", "generation_requests"), ("campaign_id", "campaigns")],
    "generation_approvals": [("request_id", "generation_requests")],
    "generation_gate_runs": [("request_id", "generation_requests")],
}
GLOBAL_TABLES = {"provider_cost_profiles", "fx_snapshots"}
SCOPED_TABLES = set(PARENTS) | {"assets", "brand_profiles", "campaigns"}


def ownership_sql() -> tuple[str, str]:
    up, down = [], []
    def view(table, query):
        up.append(f"CREATE VIEW v_scope_{table} AS {query};")
        down.insert(0, f"DROP VIEW IF EXISTS v_scope_{table};")
    def trigger(name, table, event, condition):
        up.append(f"CREATE TRIGGER {name} BEFORE {event} ON {table} WHEN {condition} "
                  "BEGIN SELECT RAISE(ABORT, 'record ownership mismatch or reassignment'); END;")
        down.insert(0, f"DROP TRIGGER IF EXISTS {name};")

    view("brand_profiles", "SELECT id, organization_id, id AS brand_profile_id, NULL AS campaign_id FROM brand_profiles")
    view("campaigns", "SELECT id, organization_id, brand_profile_id, id AS campaign_id FROM campaigns")
    for table, parents in PARENTS.items():
        column, parent = parents[0]
        view(table, f"SELECT r.id, p.organization_id, p.brand_profile_id, p.campaign_id "
                    f"FROM {table} r JOIN v_scope_{parent} p ON p.id=r.{column}")
    view("assets", """SELECT a.id, c.organization_id, c.brand_profile_id, c.id AS campaign_id
        FROM assets a LEFT JOIN scenes s ON s.id=a.scene_id
        LEFT JOIN storyboards b ON b.id=s.storyboard_id
        JOIN campaigns c ON c.id=COALESCE(a.campaign_id,b.campaign_id)""")

    for table, parents in PARENTS.items():
        column, parent = parents[0]
        trigger(f"trg_owner_{table}", table, f"UPDATE OF {column}",
                f"NEW.{column} IS NOT OLD.{column}")
        for ref_column, ref_table in parents[1:]:
            same_campaign = "" if ref_column == "parent_asset_id" else (
                "AND (p.campaign_id IS NULL OR r.campaign_id IS NULL OR p.campaign_id IS r.campaign_id)")
            condition = f"""NEW.{ref_column} IS NOT NULL AND NOT EXISTS(
                SELECT 1 FROM v_scope_{parent} p, v_scope_{ref_table} r
                WHERE p.id=NEW.{column} AND r.id=NEW.{ref_column}
                  AND p.organization_id IS r.organization_id
                  AND p.brand_profile_id IS r.brand_profile_id {same_campaign})"""
            for event in ("INSERT", "UPDATE"):
                trigger(f"trg_link_{table}_{ref_column}_{event.lower()}", table, event, condition)

    for table, columns in {
        "brand_profiles": ("organization_id",), "campaigns": ("organization_id", "brand_profile_id"),
        "assets": ("campaign_id", "scene_id"),
    }.items():
        for col in columns:
            trigger(f"trg_owner_{table}_{col}", table, f"UPDATE OF {col}", f"NEW.{col} IS NOT OLD.{col}")
    for event in ("INSERT", "UPDATE"):
        trigger(f"trg_link_assets_{event.lower()}", "assets", event, """NEW.campaign_id IS NOT NULL
            AND NEW.scene_id IS NOT NULL AND NOT EXISTS(
            SELECT 1 FROM scenes s JOIN storyboards b ON b.id=s.storyboard_id
            WHERE s.id=NEW.scene_id AND b.campaign_id=NEW.campaign_id)""")
        for table in ("generation_requests", "generation_budget_policies", "generation_provenance", "generation_spend_ledger"):
            trigger(f"trg_tenant_{table}_{event.lower()}", table, event, """EXISTS(
                SELECT 1 FROM campaigns c WHERE c.id=NEW.campaign_id
                  AND c.organization_id IS NOT NULL AND c.organization_id IS NOT NEW.tenant_id)""")
        for table in ("generation_provenance", "generation_spend_ledger"):
            trigger(f"trg_request_tenant_{table}_{event.lower()}", table, event,
                    "NOT EXISTS(SELECT 1 FROM generation_requests r WHERE r.id=NEW.request_id "
                    "AND r.tenant_id=NEW.tenant_id AND r.campaign_id=NEW.campaign_id)")
        for table, ref_col, ref_table in (
            ("generation_results", "attempt_id", "generation_attempts"),
            ("generation_provenance", "result_id", "generation_results"),
        ):
            trigger(f"trg_request_link_{table}_{event.lower()}", table, event,
                    f"NOT EXISTS(SELECT 1 FROM {ref_table} p WHERE p.id=NEW.{ref_col} AND p.request_id=NEW.request_id)")
    return "\n".join(up), "\n".join(down)
