# Database foundation

Migration: `0001_foundation`. PostgreSQL only; SQLite is not an isolation-test substitute.

| Table | Purpose / constraints |
| --- | --- |
| `organizations` | UUID, unique validated slug, name/legal name, IANA timezone, ISO currency/country, status, settings JSON, timestamps |
| `users` | Global minimal authentication identity, unique email, name/phone/provider ID, status, timestamps; FastAPI Users password hash and active/verified/superuser flags |
| `organization_memberships` | Organization/user FKs; unique pair; constrained seven-role enum; active flag; restrictive permission overrides; timestamps |
| `audit_logs` | Tenant, actor, action, entity, allowlisted before/after, IP/metadata, timestamp; database trigger rejects updates/deletes |
| `auth_sessions` | Authentication support table; hashed opaque token, user FK and creation timestamp; server enforces configured lifetime |

Alembic's own version table tracks schema history. The first migration freezes its schema; it does not call live ORM metadata to generate tables. New changes require a new migration. Downgrades delete foundation tables and are destructive; use only disposable databases or approved recovery plans.

Run migrations with a separate owner role. Runtime role `fleetpilot_app` must be NOSUPERUSER NOBYPASSRLS, unable to create roles/databases or objects in public. It receives SELECT/INSERT/UPDATE/DELETE but not TRUNCATE or schema ownership. Organizations, memberships and audit logs enable and force row security. The API fails startup with a superuser or BYPASSRLS account.

Before tenant queries, `app.user_id` permits membership discovery for that user. After validation, `app.organization_id` scopes tenant reads/writes. Settings are transaction-local. A commit/rollback clears them before a pooled connection is reused. RLS is defense against accidentally unscoped queries, not a substitute for protecting the database credentials or verifying tenant context.

User identities and sessions are accessed by the authentication adapter. Application user lists always join memberships and filter the validated organization. Audit writes have no update/delete API and are committed atomically with the business change. Operator-created organizations/owners are recorded by provisioning and the explicit development seed.

No operational tables exist. Money and trip fields from Phase 0 remain future work.
