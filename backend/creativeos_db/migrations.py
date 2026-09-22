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

MIGRATION_6_UP = """
CREATE TABLE generation_queue(
 id TEXT PRIMARY KEY,
 generation_job_id TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL DEFAULT 'QUEUED' CHECK(state IN ('QUEUED','CLAIMED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
 priority INTEGER NOT NULL DEFAULT 100,
 available_at TEXT NOT NULL,
 attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
 max_attempts INTEGER NOT NULL DEFAULT 3 CHECK(max_attempts > 0),
 claimed_by TEXT,
 claim_token TEXT,
 claimed_at TEXT,
 lease_expires_at TEXT,
 started_at TEXT,
 finished_at TEXT,
 cancel_requested_at TEXT,
 last_error_code TEXT,
 last_error_message TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(generation_job_id) REFERENCES generation_jobs(id) ON DELETE CASCADE
);
"""
MIGRATION_6_UP += """
CREATE INDEX ix_generation_queue_ready
 ON generation_queue(state, priority, available_at, created_at, id);
CREATE INDEX ix_generation_queue_lease
 ON generation_queue(state, lease_expires_at);
CREATE UNIQUE INDEX ux_generation_queue_claim_token
 ON generation_queue(claim_token) WHERE claim_token IS NOT NULL;
INSERT INTO schema_migrations(version) VALUES(6);
"""
MIGRATION_6_DOWN = """
DROP INDEX IF EXISTS ux_generation_queue_claim_token;
DROP INDEX IF EXISTS ix_generation_queue_lease;
DROP INDEX IF EXISTS ix_generation_queue_ready;
DROP TABLE IF EXISTS generation_queue;
DELETE FROM schema_migrations WHERE version=6;
"""
MIGRATIONS[6] = (MIGRATION_6_UP, MIGRATION_6_DOWN)

MIGRATION_7_UP = """
ALTER TABLE campaigns ADD COLUMN budget_currency TEXT;
ALTER TABLE campaigns ADD COLUMN budget_minor_exponent INTEGER;
ALTER TABLE campaigns ADD COLUMN near_limit_bps INTEGER NOT NULL DEFAULT 9000;
CREATE TABLE provider_cost_profiles(
 id TEXT PRIMARY KEY, provider TEXT NOT NULL, model TEXT NOT NULL,
 capability TEXT NOT NULL, quality_tier TEXT NOT NULL,
 currency TEXT NOT NULL, currency_minor_exponent INTEGER NOT NULL,
 fixed_cost_minor INTEGER, per_image_cost_minor INTEGER,
 per_second_cost_minor INTEGER, per_unit_cost_minor INTEGER,
 source_label TEXT NOT NULL DEFAULT 'LOCAL_CONFIG', version INTEGER NOT NULL,
 effective_at TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(provider, model, capability, version)
);
CREATE TABLE fx_snapshots(
 id TEXT PRIMARY KEY, from_currency TEXT NOT NULL, to_currency TEXT NOT NULL,
 from_minor_exponent INTEGER NOT NULL, to_minor_exponent INTEGER NOT NULL,
 rate_decimal TEXT NOT NULL, rate_source TEXT NOT NULL,
 rate_effective_at TEXT NOT NULL, captured_at TEXT NOT NULL, created_at TEXT NOT NULL
);
"""
MIGRATION_7_UP += """
CREATE TABLE cost_recommendations(
 id TEXT PRIMARY KEY, asset_requirement_id TEXT NOT NULL, campaign_id TEXT NOT NULL,
 budget_total_minor INTEGER, budget_currency TEXT, budget_minor_exponent INTEGER,
 committed_cost_minor INTEGER NOT NULL DEFAULT 0,
 planned_cost_minor INTEGER NOT NULL DEFAULT 0,
 near_limit_bps INTEGER NOT NULL DEFAULT 9000,
 recommended_estimate_id TEXT, created_at TEXT NOT NULL,
 FOREIGN KEY(asset_requirement_id) REFERENCES asset_requirements(id) ON DELETE RESTRICT,
 FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE RESTRICT
);
CREATE TABLE cost_estimates(
 id TEXT PRIMARY KEY, recommendation_id TEXT NOT NULL,
 provider_cost_profile_id TEXT NOT NULL, fx_snapshot_id TEXT,
 provider TEXT NOT NULL, model TEXT NOT NULL, capability TEXT NOT NULL,
 quality_tier TEXT NOT NULL, original_cost_minor INTEGER,
 original_currency TEXT NOT NULL, normalized_cost_minor INTEGER,
 normalized_currency TEXT, budget_state TEXT NOT NULL,
 is_recommended INTEGER NOT NULL DEFAULT 0 CHECK(is_recommended IN (0,1)),
 profile_snapshot_json TEXT NOT NULL, fx_snapshot_json TEXT,
 budget_snapshot_json TEXT NOT NULL, calculation_json TEXT NOT NULL,
 created_at TEXT NOT NULL,
 FOREIGN KEY(recommendation_id) REFERENCES cost_recommendations(id) ON DELETE RESTRICT,
 FOREIGN KEY(provider_cost_profile_id) REFERENCES provider_cost_profiles(id) ON DELETE RESTRICT,
 FOREIGN KEY(fx_snapshot_id) REFERENCES fx_snapshots(id) ON DELETE RESTRICT
);
"""
MIGRATION_7_UP += """
CREATE TABLE cost_overrides(
 id TEXT PRIMARY KEY, recommendation_id TEXT NOT NULL,
 selected_estimate_id TEXT NOT NULL, original_recommended_estimate_id TEXT,
 reason TEXT NOT NULL, evidence_json TEXT NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(recommendation_id) REFERENCES cost_recommendations(id) ON DELETE RESTRICT,
 FOREIGN KEY(selected_estimate_id) REFERENCES cost_estimates(id) ON DELETE RESTRICT
);
CREATE INDEX ix_cost_estimates_recommendation ON cost_estimates(recommendation_id);
CREATE INDEX ix_cost_recommendations_campaign ON cost_recommendations(campaign_id, created_at);
INSERT INTO schema_migrations(version) VALUES(7);
"""
MIGRATION_7_DOWN = """
DROP INDEX IF EXISTS ix_cost_recommendations_campaign;
DROP INDEX IF EXISTS ix_cost_estimates_recommendation;
DROP TABLE IF EXISTS cost_overrides;
DROP TABLE IF EXISTS cost_estimates;
DROP TABLE IF EXISTS cost_recommendations;
DROP TABLE IF EXISTS fx_snapshots;
DROP TABLE IF EXISTS provider_cost_profiles;
ALTER TABLE campaigns DROP COLUMN near_limit_bps;
ALTER TABLE campaigns DROP COLUMN budget_minor_exponent;
ALTER TABLE campaigns DROP COLUMN budget_currency;
DELETE FROM schema_migrations WHERE version=7;
"""
MIGRATIONS[7] = (MIGRATION_7_UP, MIGRATION_7_DOWN)

MIGRATION_8_UP = """
CREATE TABLE voice_jobs(
 id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, generation_job_id TEXT,
 provider TEXT NOT NULL, model TEXT NOT NULL, voice_id TEXT NOT NULL,
 text_snapshot TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'en',
 status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),
 output_path TEXT, duration_ms INTEGER, checksum_sha256 TEXT, error TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
 FOREIGN KEY(generation_job_id) REFERENCES generation_jobs(id) ON DELETE SET NULL
);
CREATE TABLE composition_timelines(
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, storyboard_id TEXT NOT NULL,
 target_width INTEGER NOT NULL, target_height INTEGER NOT NULL,
 aspect_ratio TEXT NOT NULL, fps INTEGER NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
 FOREIGN KEY(storyboard_id) REFERENCES storyboards(id) ON DELETE CASCADE
);
"""
MIGRATION_8_UP += """
CREATE TABLE composition_timeline_entries(
 id TEXT PRIMARY KEY, timeline_id TEXT NOT NULL, sequence INTEGER NOT NULL,
 scene_id TEXT NOT NULL, scene_version_id TEXT, generated_asset_id TEXT,
 start_ms INTEGER NOT NULL, duration_ms INTEGER NOT NULL,
 visual_path TEXT NOT NULL, audio_path TEXT,
 transition_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
 FOREIGN KEY(timeline_id) REFERENCES composition_timelines(id) ON DELETE CASCADE,
 FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
 FOREIGN KEY(scene_version_id) REFERENCES scene_versions(id) ON DELETE SET NULL,
 FOREIGN KEY(generated_asset_id) REFERENCES generated_assets(id) ON DELETE SET NULL,
 UNIQUE(timeline_id, sequence)
);
CREATE TABLE render_jobs(
 id TEXT PRIMARY KEY, timeline_id TEXT NOT NULL, render_identity TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),
 output_path TEXT NOT NULL, command_args_json TEXT NOT NULL DEFAULT '[]',
 ffmpeg_path TEXT NOT NULL, ffmpeg_version TEXT NOT NULL,
 started_at TEXT, finished_at TEXT, exit_code INTEGER,
 stdout_summary TEXT, stderr_summary TEXT, output_checksum_sha256 TEXT,
 probe_json TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 FOREIGN KEY(timeline_id) REFERENCES composition_timelines(id) ON DELETE RESTRICT
);
CREATE TABLE render_attempts(
 id TEXT PRIMARY KEY, render_job_id TEXT NOT NULL, started_at TEXT NOT NULL,
 finished_at TEXT, exit_code INTEGER, stdout_summary TEXT, stderr_summary TEXT,
 error TEXT, created_at TEXT NOT NULL,
 FOREIGN KEY(render_job_id) REFERENCES render_jobs(id) ON DELETE CASCADE
);
INSERT INTO schema_migrations(version) VALUES(8);
"""
MIGRATION_8_DOWN = """
DROP TABLE IF EXISTS render_attempts;
DROP TABLE IF EXISTS render_jobs;
DROP TABLE IF EXISTS composition_timeline_entries;
DROP TABLE IF EXISTS composition_timelines;
DROP TABLE IF EXISTS voice_jobs;
DELETE FROM schema_migrations WHERE version=8;
"""
MIGRATIONS[8] = (MIGRATION_8_UP, MIGRATION_8_DOWN)
