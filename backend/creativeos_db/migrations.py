MIGRATION_1_UP = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
CREATE TABLE brand_profiles(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, logo_path TEXT,
  palette_json TEXT NOT NULL DEFAULT '[]', fonts_json TEXT NOT NULL DEFAULT '[]',
  positioning TEXT NOT NULL DEFAULT '', audience TEXT NOT NULL DEFAULT '',
  messaging_json TEXT NOT NULL DEFAULT '[]', cta_rules_json TEXT NOT NULL DEFAULT '[]',
  prohibited_visuals_json TEXT NOT NULL DEFAULT '[]', approved_refs_json TEXT NOT NULL DEFAULT '[]',
  immutable_rules_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE campaigns(
  id TEXT PRIMARY KEY, brand_profile_id TEXT NOT NULL, title TEXT NOT NULL,
  objective TEXT NOT NULL DEFAULT '', audience TEXT NOT NULL DEFAULT '', offer TEXT NOT NULL DEFAULT '',
  cta TEXT NOT NULL DEFAULT '', format TEXT NOT NULL DEFAULT '', duration_seconds INTEGER NOT NULL DEFAULT 0,
  aspect_ratio TEXT NOT NULL DEFAULT '16:9', tone TEXT NOT NULL DEFAULT '', budget_cents INTEGER,
  status TEXT NOT NULL DEFAULT 'DRAFT', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(brand_profile_id) REFERENCES brand_profiles(id) ON DELETE RESTRICT
);
CREATE TABLE storyboards(
  id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'DRAFT', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);
"""
MIGRATION_1_UP += """
CREATE TABLE scenes(
  id TEXT PRIMARY KEY, storyboard_id TEXT NOT NULL, position INTEGER NOT NULL,
  title TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT '', duration_seconds INTEGER NOT NULL DEFAULT 0,
  script TEXT NOT NULL DEFAULT '', visual_direction TEXT NOT NULL DEFAULT '', scene_type TEXT NOT NULL DEFAULT 'REAL_UI',
  status TEXT NOT NULL DEFAULT 'DRAFT', provider_choice TEXT, cost_estimate_cents INTEGER NOT NULL DEFAULT 0,
  qa_state TEXT NOT NULL DEFAULT 'PENDING', approval_state TEXT NOT NULL DEFAULT 'DRAFT',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(storyboard_id) REFERENCES storyboards(id) ON DELETE CASCADE,
  UNIQUE(storyboard_id, position)
);
CREATE TABLE assets(
  id TEXT PRIMARY KEY, campaign_id TEXT, scene_id TEXT, asset_type TEXT NOT NULL, path TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'local', immutable_ui INTEGER NOT NULL DEFAULT 0 CHECK(immutable_ui IN (0,1)),
  provider TEXT, generation_id TEXT, width INTEGER, height INTEGER, duration_ms INTEGER, file_size INTEGER,
  approval_status TEXT NOT NULL DEFAULT 'DRAFT', created_at TEXT NOT NULL,
  FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
  FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE SET NULL
);
"""
MIGRATION_1_UP += """
CREATE TABLE generation_jobs(
  id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'DRAFT', request_json TEXT NOT NULL DEFAULT '{}', response_json TEXT,
  output_path TEXT, estimated_cost_cents INTEGER NOT NULL DEFAULT 0, actual_cost_cents INTEGER,
  error TEXT, retry_of_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
  FOREIGN KEY(retry_of_id) REFERENCES generation_jobs(id) ON DELETE SET NULL
);
CREATE TABLE qa_results(
  id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, scene_id TEXT, check_type TEXT NOT NULL,
  status TEXT NOT NULL, message TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
  FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
  FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE
);
CREATE TABLE export_jobs(
  id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, preset TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'DRAFT', output_path TEXT, settings_json TEXT NOT NULL DEFAULT '{}',
  error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);
INSERT INTO schema_migrations(version) VALUES(1);
"""
MIGRATION_1_DOWN = """
DROP TABLE IF EXISTS export_jobs;
DROP TABLE IF EXISTS qa_results;
DROP TABLE IF EXISTS generation_jobs;
DROP TABLE IF EXISTS assets;
DROP TABLE IF EXISTS scenes;
DROP TABLE IF EXISTS storyboards;
DROP TABLE IF EXISTS campaigns;
DROP TABLE IF EXISTS brand_profiles;
DELETE FROM schema_migrations WHERE version=1;
"""

MIGRATIONS = {1: (MIGRATION_1_UP, MIGRATION_1_DOWN)}

MIGRATION_2_UP = """
ALTER TABLE brand_profiles ADD COLUMN display_name TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN industry TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN icon_path TEXT;
ALTER TABLE brand_profiles ADD COLUMN brand_personality TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN tone_of_voice TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN target_market TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN pain_points_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE brand_profiles ADD COLUMN core_promise TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN proof_points_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE brand_profiles ADD COLUMN differentiation TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN prohibited_messaging_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE brand_profiles ADD COLUMN preferred_terms_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE brand_profiles ADD COLUMN prohibited_terms_json TEXT NOT NULL DEFAULT '[]';
"""
MIGRATION_2_UP += """
ALTER TABLE brand_profiles ADD COLUMN tagline TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN elevator_pitch TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN product_description TEXT NOT NULL DEFAULT '';
ALTER TABLE brand_profiles ADD COLUMN campaign_languages_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE brand_profiles ADD COLUMN approved_ui_folders_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE brand_profiles ADD COLUMN protected_screens_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE brand_profiles ADD COLUMN allowed_ui_transforms_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE brand_profiles ADD COLUMN prohibited_generative_transforms_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE brand_profiles ADD COLUMN visual_rules_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE brand_profiles ADD COLUMN default_immutable_ui INTEGER NOT NULL DEFAULT 0 CHECK(default_immutable_ui IN (0,1));
CREATE UNIQUE INDEX IF NOT EXISTS ux_brand_profiles_name_nocase ON brand_profiles(lower(name));
CREATE TABLE creative_memory(
  id TEXT PRIMARY KEY, brand_profile_id TEXT NOT NULL, decision_type TEXT NOT NULL,
  note TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'local', created_at TEXT NOT NULL,
  FOREIGN KEY(brand_profile_id) REFERENCES brand_profiles(id) ON DELETE CASCADE
);
INSERT INTO schema_migrations(version) VALUES(2);
"""
MIGRATION_2_DOWN = """
DROP TABLE IF EXISTS creative_memory;
DROP INDEX IF EXISTS ux_brand_profiles_name_nocase;
ALTER TABLE brand_profiles DROP COLUMN default_immutable_ui;
ALTER TABLE brand_profiles DROP COLUMN visual_rules_json;
ALTER TABLE brand_profiles DROP COLUMN prohibited_generative_transforms_json;
ALTER TABLE brand_profiles DROP COLUMN allowed_ui_transforms_json;
ALTER TABLE brand_profiles DROP COLUMN protected_screens_json;
ALTER TABLE brand_profiles DROP COLUMN approved_ui_folders_json;
ALTER TABLE brand_profiles DROP COLUMN campaign_languages_json;
ALTER TABLE brand_profiles DROP COLUMN product_description;
ALTER TABLE brand_profiles DROP COLUMN elevator_pitch;
ALTER TABLE brand_profiles DROP COLUMN tagline;
ALTER TABLE brand_profiles DROP COLUMN prohibited_terms_json;
ALTER TABLE brand_profiles DROP COLUMN preferred_terms_json;
ALTER TABLE brand_profiles DROP COLUMN prohibited_messaging_json;
"""
MIGRATION_2_DOWN += """
ALTER TABLE brand_profiles DROP COLUMN differentiation;
ALTER TABLE brand_profiles DROP COLUMN proof_points_json;
ALTER TABLE brand_profiles DROP COLUMN core_promise;
ALTER TABLE brand_profiles DROP COLUMN pain_points_json;
ALTER TABLE brand_profiles DROP COLUMN target_market;
ALTER TABLE brand_profiles DROP COLUMN tone_of_voice;
ALTER TABLE brand_profiles DROP COLUMN brand_personality;
ALTER TABLE brand_profiles DROP COLUMN icon_path;
ALTER TABLE brand_profiles DROP COLUMN industry;
ALTER TABLE brand_profiles DROP COLUMN description;
ALTER TABLE brand_profiles DROP COLUMN display_name;
DELETE FROM schema_migrations WHERE version=2;
"""

MIGRATIONS[2] = (MIGRATION_2_UP, MIGRATION_2_DOWN)

MIGRATION_3_UP = """
CREATE TABLE director_plans(
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  provider_mode TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'DRAFT',
  brief_json TEXT NOT NULL,
  output_json TEXT NOT NULL,
  approved_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
  UNIQUE(campaign_id, version)
);
INSERT INTO schema_migrations(version) VALUES(3);
"""
MIGRATION_3_DOWN = """
DROP TABLE IF EXISTS director_plans;
DELETE FROM schema_migrations WHERE version=3;
"""
MIGRATIONS[3] = (MIGRATION_3_UP, MIGRATION_3_DOWN)

MIGRATION_4_UP = """
ALTER TABLE scenes ADD COLUMN on_screen_copy TEXT NOT NULL DEFAULT '';
ALTER TABLE scenes ADD COLUMN subtitle_line TEXT NOT NULL DEFAULT '';
ALTER TABLE scenes ADD COLUMN transition_in TEXT NOT NULL DEFAULT '';
ALTER TABLE scenes ADD COLUMN transition_out TEXT NOT NULL DEFAULT '';
ALTER TABLE scenes ADD COLUMN motion_level TEXT NOT NULL DEFAULT 'low';
ALTER TABLE scenes ADD COLUMN asset_requirements_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE scenes ADD COLUMN provider_recommendation TEXT NOT NULL DEFAULT '';
ALTER TABLE scenes ADD COLUMN generation_method TEXT NOT NULL DEFAULT 'GENERATIVE';
ALTER TABLE scenes ADD COLUMN cost_estimate_low_cents INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scenes ADD COLUMN cost_estimate_high_cents INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scenes ADD COLUMN locked INTEGER NOT NULL DEFAULT 0 CHECK(locked IN (0,1));
ALTER TABLE scenes ADD COLUMN selected_version_id TEXT;
ALTER TABLE scenes ADD COLUMN approved_version_id TEXT;
ALTER TABLE scenes ADD COLUMN immutable_ui INTEGER NOT NULL DEFAULT 0 CHECK(immutable_ui IN (0,1));
CREATE TABLE scene_versions(
 id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, version_number INTEGER NOT NULL,
 source_type TEXT NOT NULL, provider TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
 prompt TEXT NOT NULL DEFAULT '', asset_refs_json TEXT NOT NULL DEFAULT '[]', output_path TEXT,
 cost_estimate_cents INTEGER NOT NULL DEFAULT 0, qa_state TEXT NOT NULL DEFAULT 'PENDING',
 approval_state TEXT NOT NULL DEFAULT 'DRAFT', is_selected INTEGER NOT NULL DEFAULT 0 CHECK(is_selected IN (0,1)),
 is_approved INTEGER NOT NULL DEFAULT 0 CHECK(is_approved IN (0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE, UNIQUE(scene_id, version_number)
);
INSERT INTO schema_migrations(version) VALUES(4);
"""
MIGRATION_4_DOWN = """
DROP TABLE IF EXISTS scene_versions;
ALTER TABLE scenes DROP COLUMN approved_version_id;
ALTER TABLE scenes DROP COLUMN selected_version_id;
ALTER TABLE scenes DROP COLUMN immutable_ui;
ALTER TABLE scenes DROP COLUMN locked;
ALTER TABLE scenes DROP COLUMN cost_estimate_high_cents;
ALTER TABLE scenes DROP COLUMN cost_estimate_low_cents;
ALTER TABLE scenes DROP COLUMN generation_method;
ALTER TABLE scenes DROP COLUMN provider_recommendation;
ALTER TABLE scenes DROP COLUMN asset_requirements_json;
ALTER TABLE scenes DROP COLUMN motion_level;
ALTER TABLE scenes DROP COLUMN transition_out;
ALTER TABLE scenes DROP COLUMN transition_in;
ALTER TABLE scenes DROP COLUMN subtitle_line;
ALTER TABLE scenes DROP COLUMN on_screen_copy;
DELETE FROM schema_migrations WHERE version=4;
"""
MIGRATIONS[4] = (MIGRATION_4_UP, MIGRATION_4_DOWN)

MIGRATION_5_UP = """
CREATE TABLE asset_requirements(
 id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, asset_type TEXT NOT NULL,
 purpose TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
 width INTEGER, height INTEGER, aspect_ratio TEXT NOT NULL DEFAULT '',
 duration_seconds INTEGER, priority TEXT NOT NULL DEFAULT 'NORMAL',
 status TEXT NOT NULL DEFAULT 'PENDING', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE
);
ALTER TABLE generation_jobs ADD COLUMN asset_requirement_id TEXT;
ALTER TABLE generation_jobs ADD COLUMN prompt TEXT NOT NULL DEFAULT '';
ALTER TABLE generation_jobs ADD COLUMN negative_prompt TEXT NOT NULL DEFAULT '';
ALTER TABLE generation_jobs ADD COLUMN reference_assets_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE generation_jobs ADD COLUMN aspect_ratio TEXT NOT NULL DEFAULT '';
ALTER TABLE generation_jobs ADD COLUMN duration_seconds INTEGER;
ALTER TABLE generation_jobs ADD COLUMN cost_credit_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE generation_jobs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE generation_jobs ADD COLUMN provider_snapshot TEXT NOT NULL DEFAULT '';
ALTER TABLE generation_jobs ADD COLUMN model_snapshot TEXT NOT NULL DEFAULT '';
"""
MIGRATION_5_UP += """
CREATE TABLE generated_assets(
 id TEXT PRIMARY KEY, generation_job_id TEXT NOT NULL,
 asset_requirement_id TEXT NOT NULL, output_path TEXT NOT NULL,
 output_type TEXT NOT NULL, output_metadata_json TEXT NOT NULL DEFAULT '{}',
 prompt_snapshot TEXT NOT NULL, provider_snapshot TEXT NOT NULL,
 model_snapshot TEXT NOT NULL, checksum_sha256 TEXT NOT NULL,
 review_state TEXT NOT NULL DEFAULT 'PENDING', created_at TEXT NOT NULL,
 FOREIGN KEY(generation_job_id) REFERENCES generation_jobs(id) ON DELETE RESTRICT,
 FOREIGN KEY(asset_requirement_id) REFERENCES asset_requirements(id) ON DELETE RESTRICT,
 UNIQUE(generation_job_id, checksum_sha256)
);
INSERT INTO schema_migrations(version) VALUES(5);
"""
MIGRATION_5_DOWN = """
DROP TABLE IF EXISTS generated_assets;
DROP TABLE IF EXISTS asset_requirements;
ALTER TABLE generation_jobs DROP COLUMN model_snapshot;
ALTER TABLE generation_jobs DROP COLUMN provider_snapshot;
ALTER TABLE generation_jobs DROP COLUMN retry_count;
ALTER TABLE generation_jobs DROP COLUMN cost_credit_json;
ALTER TABLE generation_jobs DROP COLUMN duration_seconds;
ALTER TABLE generation_jobs DROP COLUMN aspect_ratio;
ALTER TABLE generation_jobs DROP COLUMN reference_assets_json;
ALTER TABLE generation_jobs DROP COLUMN negative_prompt;
ALTER TABLE generation_jobs DROP COLUMN prompt;
ALTER TABLE generation_jobs DROP COLUMN asset_requirement_id;
DELETE FROM schema_migrations WHERE version=5;
"""
MIGRATIONS[5] = (MIGRATION_5_UP, MIGRATION_5_DOWN)
