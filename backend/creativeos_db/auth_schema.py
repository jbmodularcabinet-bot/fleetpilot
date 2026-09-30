"""Schema v12: authenticated sessions and explicit, audited legacy adoption."""

UP = """
CREATE TABLE auth_users(
 id TEXT PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
 password_hash TEXT NOT NULL, platform_admin INTEGER NOT NULL DEFAULT 0,
 enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE organization_memberships(
 user_id TEXT NOT NULL REFERENCES auth_users(id), organization_id TEXT NOT NULL REFERENCES organizations(id),
 role TEXT NOT NULL CHECK(role IN ('OWNER','EDITOR','VIEWER')),
 active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(user_id,organization_id));
CREATE TABLE auth_sessions(
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_users(id),
 csrf TEXT NOT NULL, expires_at INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 0,
 organization_id TEXT REFERENCES organizations(id), brand_profile_id TEXT REFERENCES brand_profiles(id),
 membership_version INTEGER);
CREATE TABLE login_attempts(username TEXT PRIMARY KEY, failures INTEGER NOT NULL, last_attempt INTEGER NOT NULL);
CREATE TABLE adoption_previews(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_users(id), session_hash TEXT NOT NULL,
 organization_id TEXT NOT NULL REFERENCES organizations(id), active_brand_id TEXT,
 scope_version INTEGER NOT NULL, legacy_brand_id TEXT NOT NULL REFERENCES brand_profiles(id),
 snapshot_json TEXT NOT NULL, digest TEXT NOT NULL, expires_at INTEGER NOT NULL,
 consumed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE ownership_audit(
 id TEXT PRIMARY KEY, preview_id TEXT NOT NULL UNIQUE REFERENCES adoption_previews(id),
 actor_id TEXT NOT NULL REFERENCES auth_users(id), organization_id TEXT NOT NULL REFERENCES organizations(id),
 legacy_brand_id TEXT NOT NULL REFERENCES brand_profiles(id), before_json TEXT NOT NULL,
 after_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER ownership_audit_no_update BEFORE UPDATE ON ownership_audit
 BEGIN SELECT RAISE(ABORT,'ownership audit is immutable'); END;
CREATE TRIGGER ownership_audit_no_delete BEFORE DELETE ON ownership_audit
 BEGIN SELECT RAISE(ABORT,'ownership audit is immutable'); END;
CREATE TABLE adoption_permits(
 brand_id TEXT PRIMARY KEY REFERENCES brand_profiles(id),
 organization_id TEXT NOT NULL REFERENCES organizations(id),
 preview_id TEXT NOT NULL REFERENCES adoption_previews(id));
DROP TRIGGER trg_owner_brand_profiles_organization_id;
CREATE TRIGGER trg_owner_brand_profiles_organization_id BEFORE UPDATE OF organization_id ON brand_profiles
 WHEN NEW.organization_id IS NOT OLD.organization_id AND NOT (
 OLD.organization_id IS NULL AND NEW.organization_id IS NOT NULL AND EXISTS(
 SELECT 1 FROM adoption_permits p WHERE p.brand_id=OLD.id AND p.organization_id=NEW.organization_id))
 BEGIN SELECT RAISE(ABORT,'brand ownership requires confirmed adoption'); END;
DROP TRIGGER trg_owner_campaigns_organization_id;
CREATE TRIGGER trg_owner_campaigns_organization_id BEFORE UPDATE OF organization_id ON campaigns
 WHEN NEW.organization_id IS NOT OLD.organization_id AND NOT (
 OLD.organization_id IS NULL AND NEW.organization_id IS NOT NULL AND EXISTS(
 SELECT 1 FROM adoption_permits p WHERE p.brand_id=OLD.brand_profile_id AND p.organization_id=NEW.organization_id))
 BEGIN SELECT RAISE(ABORT,'campaign ownership requires confirmed adoption'); END;
DROP TRIGGER trg_brand_scope_update;
CREATE TRIGGER trg_brand_scope_update BEFORE UPDATE OF organization_id ON brand_profiles
 WHEN EXISTS(SELECT 1 FROM campaigns WHERE brand_profile_id=OLD.id AND organization_id IS NOT NEW.organization_id)
 AND NOT (OLD.organization_id IS NULL AND EXISTS(
 SELECT 1 FROM adoption_permits p WHERE p.brand_id=OLD.id AND p.organization_id=NEW.organization_id))
 BEGIN SELECT RAISE(ABORT,'brand organization cannot diverge from owned campaigns'); END;
ALTER TABLE generation_requests ADD COLUMN render_job_id TEXT REFERENCES render_jobs(id);
ALTER TABLE generation_requests ADD COLUMN qa_run_id TEXT REFERENCES qa_runs(id);
CREATE TRIGGER request_render_scope BEFORE UPDATE OF render_job_id,qa_run_id ON generation_requests
 WHEN (NEW.render_job_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM v_scope_render_jobs r WHERE r.id=NEW.render_job_id AND r.campaign_id=NEW.campaign_id))
 OR (NEW.qa_run_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM qa_runs q WHERE q.id=NEW.qa_run_id AND q.render_job_id=NEW.render_job_id))
 BEGIN SELECT RAISE(ABORT,'request render/QA ownership mismatch'); END;
CREATE TRIGGER request_render_scope_insert BEFORE INSERT ON generation_requests
 WHEN (NEW.render_job_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM v_scope_render_jobs r WHERE r.id=NEW.render_job_id AND r.campaign_id=NEW.campaign_id))
 OR (NEW.qa_run_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM qa_runs q WHERE q.id=NEW.qa_run_id AND q.render_job_id=NEW.render_job_id))
 BEGIN SELECT RAISE(ABORT,'request render/QA ownership mismatch'); END;
INSERT INTO schema_migrations(version) VALUES(12);
"""

DOWN = """
DROP TRIGGER request_render_scope;
DROP TRIGGER request_render_scope_insert;
ALTER TABLE generation_requests DROP COLUMN qa_run_id;
ALTER TABLE generation_requests DROP COLUMN render_job_id;
DROP TRIGGER trg_owner_brand_profiles_organization_id;
DROP TRIGGER trg_owner_campaigns_organization_id;
DROP TRIGGER trg_brand_scope_update;
CREATE TRIGGER trg_owner_brand_profiles_organization_id BEFORE UPDATE OF organization_id ON brand_profiles
 WHEN NEW.organization_id IS NOT OLD.organization_id
 BEGIN SELECT RAISE(ABORT,'record ownership mismatch or reassignment'); END;
CREATE TRIGGER trg_owner_campaigns_organization_id BEFORE UPDATE OF organization_id ON campaigns
 WHEN NEW.organization_id IS NOT OLD.organization_id
 BEGIN SELECT RAISE(ABORT,'record ownership mismatch or reassignment'); END;
CREATE TRIGGER trg_brand_scope_update BEFORE UPDATE OF organization_id ON brand_profiles
 WHEN EXISTS(SELECT 1 FROM campaigns WHERE brand_profile_id=OLD.id AND organization_id IS NOT NEW.organization_id)
 BEGIN SELECT RAISE(ABORT,'brand organization cannot diverge from owned campaigns'); END;
DROP TABLE adoption_permits;
DROP TRIGGER ownership_audit_no_update;
DROP TRIGGER ownership_audit_no_delete;
DROP TABLE ownership_audit;
DROP TABLE adoption_previews;
DROP TABLE auth_sessions;
DROP TABLE organization_memberships;
DROP TABLE login_attempts;
DROP TABLE auth_users;
DELETE FROM schema_migrations WHERE version=12;
"""
