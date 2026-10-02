"""Schema v13: Creative Intelligence foundation and asset truth metadata."""

TRUTH_LEVELS = ("REAL_PROJECT", "APPROVED_RENDER", "AI_DERIVED", "AI_GENERATED")

def _scope_triggers(table: str) -> str:
    return f"""
CREATE TRIGGER trg_ci_{table}_scope_insert
BEFORE INSERT ON {table}
WHEN NOT EXISTS(
  SELECT 1 FROM brand_profiles b
  WHERE b.id=NEW.brand_profile_id AND b.organization_id=NEW.organization_id
)
BEGIN SELECT RAISE(ABORT, 'creative intelligence scope mismatch'); END;
CREATE TRIGGER trg_ci_{table}_scope_update
BEFORE UPDATE OF organization_id, brand_profile_id ON {table}
WHEN NEW.organization_id IS NOT OLD.organization_id
  OR NEW.brand_profile_id IS NOT OLD.brand_profile_id
BEGIN SELECT RAISE(ABORT, 'creative intelligence scope is immutable'); END;
"""

UP = """
ALTER TABLE assets ADD COLUMN truth_level TEXT
  CHECK(truth_level IS NULL OR truth_level IN ('REAL_PROJECT','APPROVED_RENDER','AI_DERIVED','AI_GENERATED'));
ALTER TABLE assets ADD COLUMN reference_fidelity_required INTEGER NOT NULL DEFAULT 0
  CHECK(reference_fidelity_required IN (0,1));

CREATE TABLE market_intelligence(
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  brand_profile_id TEXT NOT NULL REFERENCES brand_profiles(id) ON DELETE RESTRICT,
  subject TEXT NOT NULL,
  subject_type TEXT NOT NULL CHECK(subject_type IN ('BRAND','PRODUCT','SERVICE')),
  intelligence_type TEXT NOT NULL
    CHECK(intelligence_type IN ('PAIN_POINT','TRIGGER','OBJECTION','PROOF','COMPETITOR_PATTERN')),
  evidence_source TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_market_intelligence_scope
  ON market_intelligence(organization_id, brand_profile_id, active, created_at);

CREATE TABLE creative_hypotheses(
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  brand_profile_id TEXT NOT NULL REFERENCES brand_profiles(id) ON DELETE RESTRICT,
  objective TEXT NOT NULL DEFAULT '',
  audience TEXT NOT NULL DEFAULT '',
  pain_point TEXT NOT NULL DEFAULT '',
  offer TEXT NOT NULL DEFAULT '',
  angle TEXT NOT NULL DEFAULT '',
  hook TEXT NOT NULL DEFAULT '',
  proof TEXT NOT NULL DEFAULT '',
  cta TEXT NOT NULL DEFAULT '',
  format TEXT NOT NULL DEFAULT '',
  funnel_stage TEXT NOT NULL DEFAULT '',
  platform TEXT NOT NULL DEFAULT '',
  success_metric TEXT NOT NULL DEFAULT '',
  evidence_state TEXT NOT NULL DEFAULT 'INSUFFICIENT'
    CHECK(evidence_state IN ('INSUFFICIENT','LIMITED','MODERATE','STRONG')),
  unresolved_assumptions TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'DRAFT'
    CHECK(status IN ('DRAFT','READY','EXPERIMENTING','ARCHIVED')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_creative_hypotheses_scope
  ON creative_hypotheses(organization_id, brand_profile_id, status, created_at);

CREATE TABLE reference_patterns(
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  brand_profile_id TEXT NOT NULL REFERENCES brand_profiles(id) ON DELETE RESTRICT,
  reference_source TEXT NOT NULL,
  hook_pattern TEXT NOT NULL DEFAULT '',
  offer_pattern TEXT NOT NULL DEFAULT '',
  composition_pattern TEXT NOT NULL DEFAULT '',
  proof_mechanism TEXT NOT NULL DEFAULT '',
  cta_pattern TEXT NOT NULL DEFAULT '',
  format TEXT NOT NULL DEFAULT '',
  audience_stage TEXT NOT NULL DEFAULT '',
  brand_safe_adaptation_notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_reference_patterns_scope
  ON reference_patterns(organization_id, brand_profile_id, created_at);

CREATE TABLE experiments(
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  brand_profile_id TEXT NOT NULL REFERENCES brand_profiles(id) ON DELETE RESTRICT,
  hypothesis_id TEXT NOT NULL REFERENCES creative_hypotheses(id) ON DELETE RESTRICT,
  variant TEXT NOT NULL,
  campaign_external_id TEXT NOT NULL DEFAULT '',
  ad_external_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'DRAFT'
    CHECK(status IN ('DRAFT','READY','RUNNING','PAUSED','COMPLETED','ARCHIVED')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_experiments_scope
  ON experiments(organization_id, brand_profile_id, hypothesis_id, created_at);

CREATE TABLE hypothesis_evidence(
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  brand_profile_id TEXT NOT NULL REFERENCES brand_profiles(id) ON DELETE RESTRICT,
  hypothesis_id TEXT NOT NULL REFERENCES creative_hypotheses(id) ON DELETE CASCADE,
  market_intelligence_id TEXT REFERENCES market_intelligence(id) ON DELETE SET NULL,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  observation TEXT NOT NULL,
  sample_size INTEGER CHECK(sample_size IS NULL OR sample_size >= 0),
  evidence_strength TEXT NOT NULL DEFAULT 'LIMITED'
    CHECK(evidence_strength IN ('INSUFFICIENT','LIMITED','MODERATE','STRONG')),
  created_at TEXT NOT NULL
);
CREATE INDEX ix_hypothesis_evidence_scope
  ON hypothesis_evidence(organization_id, brand_profile_id, hypothesis_id, created_at);

CREATE TABLE experiment_asset_links(
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  brand_profile_id TEXT NOT NULL REFERENCES brand_profiles(id) ON DELETE RESTRICT,
  experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  asset_kind TEXT NOT NULL CHECK(asset_kind IN ('ASSET','GENERATED_ASSET')),
  asset_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(experiment_id, asset_kind, asset_id)
);
CREATE INDEX ix_experiment_asset_links_scope
  ON experiment_asset_links(organization_id, brand_profile_id, experiment_id);

CREATE TABLE generation_provider_capabilities(
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  supported_job_types_json TEXT NOT NULL DEFAULT '[]',
  estimated_cost_metadata_json TEXT NOT NULL DEFAULT '{}',
  reference_fidelity_capability TEXT NOT NULL DEFAULT 'NONE'
    CHECK(reference_fidelity_capability IN ('NONE','LOW','MEDIUM','HIGH','EXACT')),
  enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(provider, model)
);

CREATE VIEW v_scope_market_intelligence AS
  SELECT id, organization_id, brand_profile_id, NULL AS campaign_id FROM market_intelligence;
CREATE VIEW v_scope_creative_hypotheses AS
  SELECT id, organization_id, brand_profile_id, NULL AS campaign_id FROM creative_hypotheses;
CREATE VIEW v_scope_reference_patterns AS
  SELECT id, organization_id, brand_profile_id, NULL AS campaign_id FROM reference_patterns;
CREATE VIEW v_scope_experiments AS
  SELECT id, organization_id, brand_profile_id, NULL AS campaign_id FROM experiments;
CREATE VIEW v_scope_hypothesis_evidence AS
  SELECT id, organization_id, brand_profile_id, NULL AS campaign_id FROM hypothesis_evidence;
CREATE VIEW v_scope_experiment_asset_links AS
  SELECT id, organization_id, brand_profile_id, NULL AS campaign_id FROM experiment_asset_links;
""" + "".join(_scope_triggers(table) for table in (
    "market_intelligence", "creative_hypotheses", "reference_patterns",
    "experiments", "hypothesis_evidence", "experiment_asset_links",
)) + """
CREATE TRIGGER trg_ci_experiment_hypothesis_insert
BEFORE INSERT ON experiments
WHEN NOT EXISTS(
  SELECT 1 FROM creative_hypotheses h
  WHERE h.id=NEW.hypothesis_id
    AND h.organization_id=NEW.organization_id
    AND h.brand_profile_id=NEW.brand_profile_id
)
BEGIN SELECT RAISE(ABORT, 'experiment hypothesis scope mismatch'); END;
CREATE TRIGGER trg_ci_experiment_hypothesis_update
BEFORE UPDATE OF hypothesis_id ON experiments
WHEN NOT EXISTS(
  SELECT 1 FROM creative_hypotheses h
  WHERE h.id=NEW.hypothesis_id
    AND h.organization_id=NEW.organization_id
    AND h.brand_profile_id=NEW.brand_profile_id
)
BEGIN SELECT RAISE(ABORT, 'experiment hypothesis scope mismatch'); END;

CREATE TRIGGER trg_ci_evidence_links_insert
BEFORE INSERT ON hypothesis_evidence
WHEN NOT EXISTS(
  SELECT 1 FROM creative_hypotheses h
  WHERE h.id=NEW.hypothesis_id
    AND h.organization_id=NEW.organization_id
    AND h.brand_profile_id=NEW.brand_profile_id
) OR (
  NEW.market_intelligence_id IS NOT NULL
  AND NOT EXISTS(
    SELECT 1 FROM market_intelligence m
    WHERE m.id=NEW.market_intelligence_id
      AND m.organization_id=NEW.organization_id
      AND m.brand_profile_id=NEW.brand_profile_id
  )
)
BEGIN SELECT RAISE(ABORT, 'evidence scope mismatch'); END;

CREATE TRIGGER trg_ci_experiment_asset_insert
BEFORE INSERT ON experiment_asset_links
WHEN NOT EXISTS(
  SELECT 1 FROM experiments e
  WHERE e.id=NEW.experiment_id
    AND e.organization_id=NEW.organization_id
    AND e.brand_profile_id=NEW.brand_profile_id
) OR (
  NEW.asset_kind='ASSET' AND NOT EXISTS(
    SELECT 1 FROM v_scope_assets a
    WHERE a.id=NEW.asset_id
      AND a.organization_id=NEW.organization_id
      AND a.brand_profile_id=NEW.brand_profile_id
  )
) OR (
  NEW.asset_kind='GENERATED_ASSET' AND NOT EXISTS(
    SELECT 1 FROM v_scope_generated_assets a
    WHERE a.id=NEW.asset_id
      AND a.organization_id=NEW.organization_id
      AND a.brand_profile_id=NEW.brand_profile_id
  )
)
BEGIN SELECT RAISE(ABORT, 'experiment asset scope mismatch'); END;

INSERT INTO schema_migrations(version) VALUES(13);
"""

DOWN = """
CREATE TEMP TABLE ci_rollback_guard(value INTEGER CHECK(value=0));
INSERT INTO ci_rollback_guard(value)
SELECT
  (SELECT COUNT(*) FROM market_intelligence) +
  (SELECT COUNT(*) FROM creative_hypotheses) +
  (SELECT COUNT(*) FROM reference_patterns) +
  (SELECT COUNT(*) FROM experiments) +
  (SELECT COUNT(*) FROM hypothesis_evidence) +
  (SELECT COUNT(*) FROM experiment_asset_links) +
  (SELECT COUNT(*) FROM generation_provider_capabilities) +
  (SELECT COUNT(*) FROM assets
     WHERE truth_level IS NOT NULL OR reference_fidelity_required<>0);
DROP TABLE ci_rollback_guard;

DROP VIEW IF EXISTS v_scope_experiment_asset_links;
DROP VIEW IF EXISTS v_scope_hypothesis_evidence;
DROP VIEW IF EXISTS v_scope_experiments;
DROP VIEW IF EXISTS v_scope_reference_patterns;
DROP VIEW IF EXISTS v_scope_creative_hypotheses;
DROP VIEW IF EXISTS v_scope_market_intelligence;
DROP TABLE IF EXISTS experiment_asset_links;
DROP TABLE IF EXISTS hypothesis_evidence;
DROP TABLE IF EXISTS experiments;
DROP TABLE IF EXISTS reference_patterns;
DROP TABLE IF EXISTS creative_hypotheses;
DROP TABLE IF EXISTS market_intelligence;
DROP TABLE IF EXISTS generation_provider_capabilities;
ALTER TABLE assets DROP COLUMN reference_fidelity_required;
ALTER TABLE assets DROP COLUMN truth_level;
DELETE FROM schema_migrations WHERE version=13;
"""
