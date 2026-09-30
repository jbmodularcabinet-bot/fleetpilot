# Authenticated scope and legacy adoption

Baseline verified: master, bbcb32026c3dbc3364b627d79763d7d3b1459040; tracked tree clean; eight unrelated untracked files preserved. Baseline: 108 backend tests, 10 frontend tests, lint and production build pass.

## Scope path and gaps
The UI is a local FleetPilot fixture using shared localStorage; it is not wired to services. There is no tracked HTTP API or authentication. The scoped store trusts its constructor IDs. v11 prevents ownership reassignment, so adoption needs a narrow audited exception. No memberships, sessions, scope revisions or adoption audit currently exist.

## Design
Keep Python/SQLite, React/TypeScript and existing generation/QA services. Add a loopback-only same-origin HTTP application entry point; preserve untracked backend/main.py. Provision accounts and memberships via an explicit local administrator command; never seed default credentials. Store salted password hashes and hashed opaque session tokens. Cookies are HttpOnly/SameSite=Strict; API mutations require an origin check and session-bound CSRF token. The local server is not a public deployment.

Every production request authenticates the user, verifies current organization membership and brand ownership, and compares a client scope revision with server-owned session context. A database write transaction serializes authorization with scope changes/revocation; existing service transactions become nested savepoints. Actor and ownership identifiers are derived exclusively from this context. Missing/revoked/stale scope fails closed.

Membership roles: OWNER and EDITOR may produce/review/export; VIEWER is read-only. Legacy inventory and adoption additionally require a platform administrator who is an OWNER of the selected organization. Ordinary organization members cannot discover unowned data.

The React application entry point becomes an authenticated workspace. The existing fixture screens stay as a regression fixture, not a bypass route. The workspace provides sign-in, organization/brand selection, campaigns, Director approval, explicit MOCK generation, real rendering, QA, human approval and authenticated export download. All state is server-backed. Scope changes clear the workspace immediately; request epochs discard old responses; cross-tab/focus synchronization refetches authoritative context.

Adopt a complete legacy Brand Brain and its campaign aggregate into the selected organization, keeping the brand ID and content intact. Do not merge into an unrelated existing Brand Brain. Preview includes all affected records, existing tenant labels, conflicts and a digest. Confirmation is single-use, user/session/scope-bound, expiring and transactional. Recompute the digest before adoption. Mixed ownership, multiple contradictory tenant labels or duplicate brand names block adoption. Unbound assets remain quarantined for manual investigation. Audit preserves before/after evidence; only a transaction-local permit enables NULL-to-owned changes. No background or inferred adoption.

## Execution
1. Add adversarial auth/scope tests and verify failures.
2. Add v12 schema, session/membership authentication and atomic request context.
3. Add explicit adoption preview/confirmation with conflict and rollback tests.
4. Add authenticated API and connect existing production services; preserve provider abstraction and mark MOCK outputs clearly.
5. Add selector/workflow UI and tests for persistence, stale responses and cross-tab switching.
6. Run full backend/frontend, lint, TypeScript/build, migration checks and two-user scoped HTTP/browser acceptance. Record exact results; commit only after all gates pass. Do not deploy.

## Acceptance focus
Two distinct authenticated users in different organizations complete sign-in through export, without sharing visibility or authority. Test membership removal, forged selectors and record IDs, stale revisions, queue/QA/approval/export boundaries, adoption conflicts and ambiguous legacy data. Preserve legacy unscoped regression tests as internal-service compatibility only.

## Implementation and operating boundary

Schema v12 adds auth_users, organization_memberships, auth_sessions, login_attempts,
adoption_previews, ownership_audit and adoption_permits. generation_requests gains
render_job_id and qa_run_id with INSERT/UPDATE scope guards. Existing v11 ownership
guards stay active; only a matching adoption permit allows NULL-to-owned changes.

The request path is:
HttpOnly session cookie -> enabled user -> current membership/version -> server session
organization/brand/revision -> scoped store -> existing campaign services.
Client ownership fields are rejected on campaign creation. Review/export actors come
from the session. CSRF and same-origin/Host checks guard HTTP mutations. The server
binds only 127.0.0.1. Read and write requests revalidate membership and brand ownership.
PBKDF2-SHA256 passwords use random salts and 600,000 iterations; session tokens are
random, hashed at rest, and expire after eight hours. There are no default accounts.

The new browser entry point intentionally replaces the fixture-only runtime surface:
the old screens had no authenticated service path and persisted shared FleetPilot state.
App.tsx and its ten tests remain unchanged as regression fixtures; they are not bundled
as an alternate unauthenticated route. The authenticated workspace exposes the requested
minimum production sequence. It is not a full port of every fixture editing control.

Organization changes persist an organization-only context and clear the active brand.
Brand changes increment a server revision. Every dependent campaign, queue, QA, approval,
cost, export, media URL and adoption preview is cleared before loading the new context.
Late responses are discarded; a rejected mutation is never replayed against another
brand. BroadcastChannel, a nonsecret localStorage notification, focus and visibility
events refresh other tabs. Reload restores server-owned context.

Generation remains behind the existing provider contract. This entry point enables
only an explicitly labelled local MOCK visual and mock voice; FFmpeg rendering,
checksum/probe QA, release checks, human review and export use the existing services.
Recorded provider/render failures are retained. Files are served only after scoped
authorization; the output tree is not a public static directory. New output directory
names hash organization, brand and campaign IDs, including imported legacy identifiers.

Adoption is whole-brand ownership assignment, not a merge into the selected brand.
The selected organization is the proposed owner; an existing active brand is optional.
A platform administrator must also have current OWNER membership in that organization.
Preview shows destination, brand, affected record counts and conflicts. Confirmation
requires an explicit checkbox/action; it binds actor, session, context revision,
snapshot digest and expiry. Changed records, duplicate names, conflicting tenant labels,
inconsistent parent links and destination idempotency conflicts block confirmation.
Ownership and tenant metadata updates, before/after audit, permit cleanup and preview
consumption share one transaction. Original Brand Brain content and record IDs remain.
Unbound assets remain quarantined for manual investigation and are not silently adopted.

## Local operation

Run commands from backend. Back up a real database and stop its writers before a
deliberate schema upgrade. No existing production/proof database was upgraded here.

- Migrate: python -m creativeos_db.admin --db <database-path> migrate
- Create user: python -m creativeos_db.admin --db <database-path> user <username>
  (password is prompted securely; add --platform-admin only for an authorized administrator)
- Create organization: python -m creativeos_db.admin --db <database-path> organization <name> <slug>
  (EXTERNAL is the default; NATIVE and ecosystem_key are explicit data)
- Create brand: python -m creativeos_db.admin --db <database-path> brand <organization-id> <name>
- Grant membership: python -m creativeos_db.admin --db <database-path> membership <user-id> <organization-id> OWNER
- Revoke membership: python -m creativeos_db.admin --db <database-path> revoke <user-id> <organization-id>
- Build frontend from app: npm.cmd run build
- Start local workspace from backend:
  python -m creativeos_db.server --db <database-path> --output <output-directory> --dist ../app/dist --port 8000
- Open http://127.0.0.1:8000. This entry point serves frontend and API on the same origin.

Schema rollback 12 -> 11 is supported before authentication/workflow data exists.
Rollback refuses to discard users, adoption evidence or render/QA bindings; restore a
verified pre-upgrade backup for a populated database. Forward migration failures are
atomic. No existing source files, unrelated patch scripts or untracked main.py are changed.

## Verification commands and acceptance

Final status: PASS for the local authenticated gate (2026-09-30).
- Full backend: 136 tests, OK, 79.224s, exit 0 (includes all 108 baseline tests).
- Full frontend: 13 tests, 2 files, PASS, 5.99s, exit 0.
- Lint: 0 warnings, 0 errors, exit 0.
- Explicit TypeScript: exit 0.
- Production build: PASS, exit 0.
- Migration checks: v11 -> v12 -> v11 -> v12 data preservation, atomic failed forward
  migration, nonempty authentication rollback refusal and prior migration suites all PASS.
- Final Chromium acceptance: PASS, no JavaScript page exceptions; both users reached approved
  export/download, all bidirectional foreign probes denied, cross-tab/reload/adoption PASS.
- Post-acceptance database integrity/FK checks, immutable adoption audit and two approved exports: PASS.
- git diff --check: PASS. No deployment or live-provider calls.

- backend: python -m unittest discover -s tests -v
- app: npm.cmd test
- app: npm.cmd run lint
- app: npx.cmd tsc -b --pretty false
- app: npm.cmd run build
- backend: python -m tests.run_authenticated_acceptance
  with CREATIVEOS_PLAYWRIGHT_MODULE pointing to an installed playwright/index.mjs or
  playwright-core/index.mjs and its Chromium browser available. The runner also supports
  the normal playwright package resolution when that variable is omitted.
  Verified runtime used C:/Users/User/Documents/ChatGPT/FleetPilot/node_modules/playwright-core/index.mjs.
  The runner creates/disposes its own database, accounts, loopback server and output files.
  Optional CREATIVEOS_ACCEPTANCE_SCREENSHOT writes a local screenshot.

Acceptance uses two independent browser contexts and separate organizations. Each signs
in, selects an organization and brand, creates a campaign, generates strategy, approves
the storyboard, generates/views a MOCK preview, passes real QA, accepts human review,
exports and downloads the result. Bidirectional foreign campaign, queue, QA, approval,
cost, media, export and forged-selector probes must all be denied. Cross-tab switching
must remove the old campaign/video/export, survive reload and deny old-brand access.
The administrator previews and explicitly adopts a legacy brand; it becomes selectable.
The runner checks no browser exceptions, database integrity, the adoption audit and two
approved exports. Backend tests also cover membership revocation, stale sessions,
authorization/commit serialization, failure-history retention, ambiguous adoption,
transactional adoption rollback and v11/v12 migration forward/rollback safety.

## Limits and next phase

The verified release gate is local authenticated operation with MOCK generation.
There is no public deployment, paid/live generation, identity-provider integration,
password recovery, MFA or distributed worker authorization in this change. Local
administrators and direct filesystem/SQLite access remain trusted. Database transactions
serialize local production work; a public multi-host service needs a separate worker
and authorization design.

Legacy adoption changes record ownership without moving or rewriting original files.
Old media outside the configured scoped output tree is not automatically served.
Historical requests without an explicit render/QA binding cannot advance through the
new scoped preview/QA/review endpoints until deliberately reconciled; no ambiguous binding is inferred.

Recommended next phase: an explicit operational rollout plan covering identity provider,
TLS/session operations, backup/restore rehearsal, legacy artifact/link reconciliation and
authenticated background workers, followed by separately authorized live-provider
acceptance. No Agency Mode, publishing, performance ingestion or billing was added.


## Files changed

- AUTHENTICATED_SCOPE.md
- CURRENT_STATE.md
- PROJECT_MEMORY.md
- TEST_MATRIX.md
- app/src/main.tsx
- app/src/Workspace.tsx
- app/src/Workspace.css
- app/src/scope-client.ts
- app/src/scope-client.test.tsx
- app/tests/authenticated-acceptance.mjs
- backend/creativeos_db/admin.py
- backend/creativeos_db/adoption.py
- backend/creativeos_db/api.py
- backend/creativeos_db/auth.py
- backend/creativeos_db/auth_schema.py
- backend/creativeos_db/server.py
- backend/creativeos_db/workflow.py
- backend/creativeos_db/store.py
- backend/creativeos_db/migrations.py
- backend/tests/repro_fixtures.py
- backend/tests/test_brand_brain.py
- backend/tests/test_cost_optimizer.py
- backend/tests/test_director.py
- backend/tests/test_generation.py
- backend/tests/test_generation_engine.py
- backend/tests/test_golden_path.py
- backend/tests/test_isolation.py
- backend/tests/test_media.py
- backend/tests/test_multibrand.py
- backend/tests/test_qa.py
- backend/tests/test_queue.py
- backend/tests/test_store.py
- backend/tests/test_storyboard.py
- backend/tests/test_adoption.py
- backend/tests/test_auth_migrations.py
- backend/tests/test_authenticated_api.py
- backend/tests/test_authenticated_http.py
- backend/tests/test_authenticated_scope.py
- backend/tests/run_authenticated_acceptance.py

Existing backend test edits only advance latest-schema assertions from 11 to 12; all original behavior assertions remain. New tests and the browser runner provide the authenticated/adoption evidence. Eight baseline untracked files are excluded.
