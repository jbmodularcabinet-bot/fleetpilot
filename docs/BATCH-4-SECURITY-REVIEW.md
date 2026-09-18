# Batch 4 security review

Reviewed 2026-09-16 against source, real PostgreSQL integration tests and browser workflows. This is a scoped engineering review, not an external penetration test or production security certification. Existing authentication, session, tenant context, restrictive permission overrides and immutable audit infrastructure are retained.

## Access and ownership

| Concern | Implemented control and evidence |
| --- | --- |
| IDOR / BOLA / known foreign UUIDs | Every trip lookup applies active organization scope; foreign trip/detail/history/assignment/mutation IDs return 404. Tests populate both tenants and attack reads, counts, search, updates, transitions, cancellation, completion and assignments. |
| Tenant isolation | All three new tables force PostgreSQL RLS. Composite foreign keys include organization for customers, drivers, vehicles, trips and assignment history. Restricted runtime-role tests independently verify foreign-row invisibility, no-context denial and blocked cross-tenant references. |
| Cross-driver access | Own endpoints require an active driver profile linked to the authenticated account, and filter by its driver ID. Trip RLS also restricts DRIVER accounts to their own current trip references. A reassigned-away trip is no longer visible to the previous driver. Same-tenant unrelated trips and other-tenant trips are tested. |
| Permission bypass | Every route enforces explicit capabilities server-side. Owner/admin/manager/dispatcher receive operational capabilities; Driver receives only own read/transition. Accounting/maintenance cannot call operational routes. Restrictive membership overrides are rechecked after obtaining the organization write lock. Assignment and dispatch additionally require `dispatch.manage`. |
| Driver data minimization | Own-trip responses exclude operator notes, actor IDs, internal customer references and cancellation details. Own timelines omit operator notes/actor IDs. No driver endpoint lists tenant-wide master resources or trips. |
| Privilege escalation / mass assignment | Strict request schemas reject organization, actor, status, milestone, source, generated trip number and other unexpected fields. Profile updates, assignment, transitions, notes, cancellation and closeout are separate commands. No generic status PATCH exists. |

RLS protects ownership and the driver row boundary; application permission resolution remains authoritative for individual capabilities. Non-driver membership in the active tenant is not itself a database implementation of every RBAC capability. Runtime database credentials are trusted server infrastructure, never client credentials. The application refuses superuser/BYPASSRLS runtime connections. Database administrators remain outside the untrusted-client threat model.

## Workflow integrity

| Concern | Implemented control and evidence |
| --- | --- |
| Unsafe transitions | Explicit action-to-milestone table; server checks exact predecessor. Database trigger independently rejects invalid milestone/status progression. Tests cover every allowed action, all out-of-order operational action combinations and the six requested invalid workflows. |
| Stale or concurrent actions | Every existing-trip command requires `expected_version`. Writes serialize through the established organization lock. Concurrent identical dispatches yield one success and one conflict; failed requests do not produce extra events. |
| Assignment conflicts | Active same-tenant resources, paired vehicle/driver, conservative overlapping reservation blockers, and dispatch-time active-work blockers. Partial unique indexes independently prevent simultaneous operational trips on one vehicle/driver. Master-resource deactivation guards prevent invalidating open work. |
| Completed-trip mutation | Application terminal checks and a database trigger reject ordinary changes to completed/cancelled trips. Tests attempt metadata/notes/assignment/transition/cancel changes and direct SQL mutation/deletion. Delivered requires separate reviewed closeout; it is not automatically complete. |
| Milestone tampering | No update/delete API or RLS policies; immutable trigger also rejects privileged SQL history changes. Actor/source/time are server-derived. Event sequence uniqueness and ordered reads retain both departure milestones. |
| Assignment-history tampering | One current row per trip. Trigger allows a current assignment to close once, retaining all identity/resource fields; ended rows cannot be rewritten or deleted. Fleet-master assignment history is independent. |
| Audit tampering / partial writes | Existing immutable audit table and transaction boundaries retained. Safe action metadata records fields/state/version rather than secrets or full contact/note contents. A forced audit-insert failure test verifies rollback of trip state/version and new milestone rows. |

Milestone immutability prevents rewriting recorded events. It is not cryptographic attestation of a physical delivery. API commands atomically produce milestones and audit records; this review does not claim arbitrary trusted database scripts automatically synthesize those records.

## Query, session and input safety

- SQLAlchemy expressions bind values. Sort fields and direction are literal allowlists; search escapes SQL LIKE wildcards. Pagination is bounded. UUID and typed filters reject malformed inputs. No user-supplied SQL fragments are used.
- Aware timestamps, ordered schedules, coordinate ranges/pairs, paired assignment IDs, bounded strings, cargo values/units and cancellation reasons are validated server-side. No upload, external URL fetch or new third-party integration is introduced.
- Existing hashed sessions, membership checks, origin checks, login controls and API middleware are reused. The complete foundation suite remains part of regression verification; no new session or login bypass is added.
- React renders user text without raw HTML injection. Frontend permission/state hiding supplements server enforcement. Server-rendered routes retain existing session guards.

## Findings and resolution

No unresolved release-blocking finding was identified in the tested Batch 4 scope. Implementation review specifically tightened initial-assignment authorization to require `dispatch.manage`, added same-tenant cross-driver tests, and guarded customer deactivation alongside vehicles/drivers. The final tests exercise those controls. No tests were relaxed to allow a forbidden transition or foreign access.

## Residual limits and deployment risks

- Scheduling is conservative, not a full planner: scheduled windows or a 24-hour fallback, no travel/rest/turnaround/late-running predictions. Delivered resources stay reserved until closeout. See [exact rules](TRIP-LIFECYCLE.md).
- Per-organization serialization and bounded lists favor consistency. Production contention, large-fleet query plans and load/soak behavior are **UNVERIFIED**. List rendering currently performs bounded related-record lookups.
- Historical trip resource IDs are immutable after closeout, but displayed master names/unit labels reflect current master records; there are no historical label snapshots.
- No backdating, administrative corrections, offline queue or generic idempotency-key replay is implemented. Reload after uncertain request outcomes; stale versions are rejected.
- Production deployment, HTTPS/ingress, Docker-host execution, remote CI, backup/restore drills and independent penetration testing are **UNVERIFIED**. Dependency consistency checks do not establish absence of vulnerabilities; a fresh online vulnerability assessment is **UNVERIFIED**.
- Inherited per-process rate limiting, CSP hardening, account lifecycle and production observability remain readiness work. No Batch 5 feature or production-readiness claim is made.
