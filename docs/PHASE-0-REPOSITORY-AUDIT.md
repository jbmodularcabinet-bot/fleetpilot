# FleetPilot — Phase 0 Repository Audit

Date: 2026-09-16  
Batch: 1 — Repository audit  
Status: PASS for audit completion; application readiness is not established.

## Scope and authority

The supplied canonical build specification contains the user's request. Section 90 explicitly requires inspection, an audit, an exact Batch 2 recommendation, and then a stop. No application implementation is included in this batch.

The two supplied images establish visual direction. Text and example values inside them are reference content, not instructions to seed real financial or operational records. This audit preserves the approved product structure and branding.

Sources inspected:

- Specification: `C:/Users/User/.codex/attachments/1c359c56-bbfd-4fa0-b54e-39d7c26dde74/pasted-text.txt`.
- Owner reference: `C:/Users/User/AppData/Local/Temp/codex-clipboard-c4aedf1c-cef0-434a-8d58-871c1562d0c7.png`.
- Driver reference: `C:/Users/User/AppData/Local/Temp/codex-clipboard-ee819d5f-5666-43f5-a438-ce4dc8b870ce.png`.

The image names in the specification differ from the supplied filenames. The supplied owner and driver images are treated as references A and B respectively. Original logo artwork, font files, and independent photography assets are not present in the repository; do not invent a replacement logo.

## Repository evidence

Workspace: `C:/Users/User/Documents/ChatGPT/FleetPilot`.

| Inspection | Observed result |
| --- | --- |
| Initial directory listing including hidden entries | Only `.git` |
| `git status --short --branch` | `No commits yet on master`; no working files before audit |
| `git ls-files` | No tracked files |
| `git log -5 --oneline` | No commits; Git reports unborn branch |
| `git remote -v` | No configured remotes |
| `rg --files --hidden -g '!.git' -g '!node_modules'` | No project files |
| Independent recursive filesystem check excluding `.git` | No project files |
| Applicable ancestor `AGENTS.md` checks | None found |
| Node / npm | Node 24.20.0; npm 11.19.0 available |
| Python / Docker / PostgreSQL CLI command discovery | Not found on current PATH; installation elsewhere is unverified |

No source code, hidden application configuration, lockfiles, environment files, or deployment manifests were found outside Git metadata. No existing code was modified or removed. No remote infrastructure was supplied or inspected, so absence locally does not establish absence in an external account.

## Current architecture and reusable work

There is no application architecture yet. The repository is an initialized, empty Git repository. There is no existing UI, driver app, backend, auth integration, database schema, migration history, storage integration, API, queue, CI pipeline, or test suite.

Reusable inputs are the specification and the two approved visual references. There are no reusable implementation modules or components, and no major replacement or data migration is proposed. Code regression risk is currently absent; architecture and requirements risks remain.

## Implementation mapping

| Required area | Current implementation | Planned batch |
| --- | --- | --- |
| Auth, organizations, memberships, seven roles, tenant isolation, audit logs | Absent | 2 |
| Design tokens, desktop shell, mobile shell, shared UI primitives | Absent | 2; expand with feature batches |
| Customers, vehicles, drivers, permission-aware CRUD | Absent | 3 |
| Bookings, trips, transition engine, assignments, activity history | Absent | 4 |
| Dispatch board and resource availability | Absent | 5 |
| Driver home, next action, progress, navigation, issues, profile | Absent | 6 |
| POD, private files, signatures, expense capture and verification | Absent | 7 |
| Contribution and margin calculations | Absent | 8 |
| Owner dashboard, calculated KPIs, recent trips, decision cards | Absent | 9 |
| Maintenance schedules, jobs, documents, expiry handling | Absent | 10 |
| Billing, payments, receivables | Absent | 11 |
| GPS adapters and explicitly simulated live fleet | Absent | 12 |
| Deterministic alerts, recommendations, daily brief | Absent | 13 |
| Grounded Ask FleetPilot | Absent | 14, after operational data validation |
| Release hardening, production migrations, full golden flows | Absent | 15; foundational checks start in Batch 2 |
| Documentation, CI, validation, security, observability | Absent | Start in Batch 2; maintain throughout |

## Visual reference audit

### Owner command center

The app within reference A uses a dark navy left sidebar, a slim search/account bar, a light content surface, compact white cards, and the approved navigation groups. Preserve this hierarchy:

1. Owner Dashboard title and date context.
2. Five KPI cards: revenue, trips, active/idle trucks, collections risk, approvals.
3. Revenue and profitability chart on the left; fleet status and recent trips on the right.
4. A full-width daily brief beneath the operational summary.

Reference A is a promotional composition containing an application screenshot. Its outer headline, truck photograph, explanatory callouts, and footer are presentation material, not additional dashboard panels. The application should reproduce the inner dashboard layout with responsive adaptations.

Use the specification's Inter typography and locked tokens: navy `#08111F`, slate `#162235`, mint `#2BE0A7`, blue `#3B82F6`, amber `#F5A524`, red `#F04444`, cloud `#F6F8FA`, white `#FFFFFF`. Retain semantic status meanings and accompanying text.

### Driver application

Reference B shows eleven separate mobile screens, not a single phone gallery to implement. Preserve the mobile hierarchy, high contrast, large touch targets, compact trip summary, route stops, one primary next-action button, and the Home / Trips / Expenses / Alerts / Profile tab bar.

The reference covers login, home, details, progress, navigation, pickup, POD, expenses, issue categories, alerts, and profile. Navigation hands off to Google Maps. Pickup checks, POD attachments/signature, and expense capture belong to focused screens. Test at 360–430 px widths without horizontal overflow.

## Specification conflicts and technical risks

| Issue | Required resolution / proposed treatment |
| --- | --- |
| Pickup arrival and loading completion are shown as separate actions but lack corresponding canonical states | Before Batch 4, define validated milestone events within `TO_PICKUP` and `LOADING`, or explicitly amend the enum. Recommended: preserve canonical states and persist milestones; do not rely on client-only flags. |
| Reference revenue of PHP 2.49M and gross profit of PHP 1.34M imply about 53.8%, not the displayed 35.1% | Treat image figures as illustrative. Use the specification's contribution formula and compute margin from the same revenue/cost basis. Never copy inconsistent sample metrics. |
| Dashboard says gross profit; specification defines gross contribution | Document the exact cost basis and use consistent labels. Do not imply accounting net profit. |
| Revenue Today does not specify earned revenue versus invoice or payment date | Define recognition and reporting rules before Batch 8/9, using the organization's local day and explicit source records. |
| Currency and time zone vary by organization | Store organization settings; use decimal-safe amounts and UTC instants with local-date reporting. Define rounding, zero-revenue margin, reversals, and duplicate handling. |
| No established identity provider selected | Use established OIDC authentication. Proposed local reference provider: Keycloak with a replaceable production issuer. Validate library/provider compatibility during Batch 2; do not build password/OTP cryptography. |
| Driver reference depicts phone OTP; provider not configured | Keep OTP as an explicit integration requirement. Batch 2 should use a real configured OIDC login; do not show a fake Send OTP flow. |
| Tenant leaks through joins, files, queues, cache, or AI context | Derive tenant access from authenticated membership; enforce tenant-scoped queries, composite constraints and PostgreSQL row security. Extend negative tests as each resource is added. |
| Global users versus tenant-owned business records | Keep identity minimal and global; access organization-specific user information through memberships. Never expose a global user directory. |
| Driver ownership restriction extends beyond role checks | Resolve the authenticated user's driver record inside the active organization and constrain trips, files, events, and expenses accordingly. |
| Double assignment and concurrent status changes | Use transactional checks, expected versions, database constraints, and idempotency keys. UI availability checks alone are insufficient. |
| Offline events may arrive late or twice | Persist event IDs, capture and receipt times, pending attachments, retries, conflict outcomes, and visible sync status. Mark offline support partial until tested. |
| Private photos and signatures | Authorize upload and retrieval, enforce limits and content validation, scope object keys, and use short-lived signed retrieval. Do not store public attachment URLs. |
| Movement detection has no provider yet | Define freshness and unknown-speed behavior. Never claim safety enforcement from simulated or stale telemetry. |
| Owner approvals lack a dedicated entity; costs include categories absent from driver entry | Model approvals and their audit trail before Batch 9; define controlled cost allocation and categories before Batch 8. Driver entry may remain a smaller subset. |
| Redis, worker, database and storage not configured | Provide reproducible local services and health checks. Runtime availability is a prerequisite for claiming integration tests passed. |
| Approved logo available only inside raster compositions | Preserve supplied artwork; use a faithful extraction or obtain original assets during UI implementation. Do not generate a new mark. |
| Release prerequisites untested | Production readiness remains blocked until every Section 86 gate passes. An audit PASS is not a product release PASS. |

## Recommended architecture

Use the preferred stack because there is no working stack to preserve:

- `apps/web`: Next.js, React, strict TypeScript, Tailwind; shared design tokens and reusable components; responsive driver PWA under `/driver`.
- `apps/api`: FastAPI, typed request/response schemas, domain services, tenant-scoped repositories, SQLAlchemy and Alembic migrations.
- PostgreSQL: authoritative records, decimal money, tenant-aware constraints and row security using a non-owner runtime role without row-security bypass.
- Established OIDC provider: server-side web sessions, secure cookies, token validation at the API, and database-backed membership authorization.
- Redis and worker: retryable background work; introduce domain jobs in their relevant batches.
- S3-compatible storage: private objects and signed access; local development may use MinIO.
- A same-origin web/API boundary to simplify cookie, CSRF and browser security. Explicitly verify mutation protection; authentication alone is insufficient.

This is a design recommendation, not installed infrastructure. Pin supported, compatible versions when scaffolding. Keep modules in a single repository and avoid premature microservices. Business state and calculations remain server-authoritative.

## Exact Batch 2 scope — Foundation

### 1. Reproducible repository and service setup

Create `apps/web`, `apps/api`, `infra`, and test directories. Add dependency manifests and lockfiles, strict typing, linting, build commands, environment templates containing no secrets, and setup documentation. Configure PostgreSQL and the local OIDC provider; define storage and queue configuration without claiming domain features are implemented. Add CI for available checks and service-backed integration tests.

### 2. Identity, tenancy, and permissions

Implement login/logout/session handling with the established provider and organization selection based only on verified memberships. Deny missing, suspended, or revoked memberships. Introduce Owner, Manager, Dispatcher, Driver, Accounting, Maintenance, and Admin roles. Treat Admin as organization-scoped unless a separate platform-admin model is later specified. Default unspecified permissions to deny; document the matrix before enabling endpoints.

Do not allow browser-supplied role or organization claims to grant access. Organization switching must reauthorize membership. Include session expiry, invalid token, CSRF, issuer/audience validation, and login abuse controls in the foundation tests.

### 3. Initial database migration

Create `organizations`, `users`, `organization_memberships`, and append-only `audit_logs` with indexes, timestamps, membership uniqueness, organization status and settings. Establish tenant transaction context and row-security policies. Membership/permission mutations and their audit records must be committed atomically. Keep database owners/migration privileges separate from runtime privileges.

Provide opt-in synthetic development fixtures for Demo Logistics Corp. and a second organization for isolation tests. Do not create real fleet records or seed illustrative dashboard revenue in this batch. Production startup must not auto-seed demo identities or credentials.

### 4. Foundation API

Implement `/api/v1/me`, authorized organization listing/selection, organization settings, and member/role management for permitted roles. Define consistent validation and error responses. Add liveness and dependency readiness checks, request IDs, structured logs with sensitive-data redaction, and an error-monitoring integration boundary. No trip, finance, GPS, or AI endpoints yet.

### 5. Approved visual shells

Implement `/login`, the desktop shell at `/dashboard`, organization/user/role settings, and the mobile shell at `/driver`. Build tokens, logo usage, Sidebar, TopNav, StatusBadge, EmptyState, LoadingState and ErrorState. Preserve the approved navigation taxonomy; future modules must be explicitly unavailable rather than dead links or pretend functionality.

The dashboard and driver shell should show truthful empty states. The fully calculated owner dashboard belongs to Batch 9; the functional driver trip flow belongs to Batch 6. Verify visible focus, keyboard interaction, readable contrast, accessible labels, and mobile touch targets.

### 6. Documentation and verification

Initialize all eleven required documents: `PRODUCT.md`, `ARCHITECTURE.md`, `DATABASE.md`, `TRIP-STATE-MACHINE.md`, `PERMISSIONS.md`, `API.md`, `DESIGN-SYSTEM.md`, `DRIVER-APP.md`, `TESTING.md`, `ROADMAP.md`, and `RELEASES.md`. Distinguish implemented behavior from planned behavior. Record the state-machine conflict for resolution in Batch 4.

Batch 2 exit gates:

- Clean installation and documented startup work; initial migration passes against an empty PostgreSQL database.
- Real login, logout, expiry handling, and membership-authorized organization switching pass.
- Org A cannot read or change Org B organization, membership, or audit data, including direct-ID requests and database row-security tests.
- Every role has positive and negative permission tests; revoked membership stops access.
- Permission/settings writes persist, validate inputs, and create immutable audit entries.
- Desktop and mobile shells render and handle loading, empty, unauthenticated and error states.
- Typecheck, lint, unit tests, PostgreSQL integration tests, relevant browser E2E, and production build pass with recorded results.
- Manual browser verification at desktop and 360/390/430 px widths is documented.

Vehicle/trip/customer/file/driver/AI isolation tests remain mandatory in their respective batches; they cannot pass before those domains exist. The full golden flows are not Batch 2 completion criteria and remain release blockers.

## Batch report

**FLEETPILOT BATCH REPORT**

- **Batch:** 1 — Phase 0 repository audit.
- **Status:** PASS — requested audit completed; no application readiness claim.
- **Implemented:** Repository inventory, visual review, implementation gap map, technical risks, recommended architecture and exact Batch 2 scope.
- **Files Created:** `docs/PHASE-0-REPOSITORY-AUDIT.md`.
- **Files Modified:** None of the pre-existing repository files.
- **Database Changes:** None.
- **API Changes:** None.
- **UI Changes:** None.
- **Tests Added:** None; there is no application to test.
- **Tests Executed:** Repository/Git inventory and runtime command discovery only. Typecheck, lint, unit, integration, UI/E2E and build are not runnable because their source/configuration does not exist.
- **Results:** Empty, uncommitted repository confirmed; no reusable code or existing infrastructure configuration found.
- **Manual Verification:** Reviewed both supplied visual references and the canonical specification; no running application exists for browser verification.
- **Known Limitations:** External infrastructure unverified; no auth/provider configuration, original design asset pack, or executable application.
- **Risks:** Tenant isolation, authentication setup, workflow gaps, financial definitions, runtime provisioning, offline consistency, private-file security.
- **Recommended Next Batch:** Batch 2 — Foundation, restricted to the scope and exit gates above.

Stopped after Phase 0 as requested in Section 90. No application build, dependency installation, deployment, or unrelated modification was performed.
