# Batch 13 security review

Scope: operational revenue, shared adjustments and computed contribution. This is an internal engineering review, not an independent assessment. Final executed gates are recorded in BATCH-13-REPORT.md.

## Controls inspected

- IDOR/BOLA/tenant boundaries: UUID validation, explicit organization filters, same-tenant composite parent references and forced RLS on revenue/projection. The shared adjustment table retains expense RLS and adds a separate revenue-parent policy. Known foreign UUIDs do not authorize reads, review, void, corrections or list results.
- Driver/role boundaries: no driver financial capabilities or Driver UI financial fetches; dispatcher and maintenance roles denied by default. Owner/admin/manager/accounting can read/create/review/ordinary void subject to restrictive overrides. Only owner/admin can create/reverse shared administrative adjustments. RLS excludes drivers from revenue and projection independently of frontend visibility.
- Mutation authorization: organization write lock, renewed membership/capability checks, DB role/actor guards and current authorization before idempotent replay. Same-key changed-body commands conflict; stale event sequences conflict. Audit/event/projection/receipt commit atomically.
- History integrity: original revenue amount/type/currency/identity/created fields are DB-immutable. Review and ordinary void are explicit transitions. Completed-trip void uses a shared append-only adjustment. Reversals append a compensating event and must reverse the latest active entry first. Direct projection edits are trigger-rejected. No generic PATCH/DELETE or arbitrary target-type mutation exists.
- Decimal and total tampering: strict decimal strings; positive bounded NUMERIC source amounts; authoritative Decimal subtraction/division/ROUND_HALF_UP. Client totals, margin, status, organization and actors are forbidden schema fields. Negative contribution is allowed, negative effective source charges are rejected.
- Cost integrity: existing effective expense revision/overlay query, no copied expense rows. Only reviewed non-voided costs enter contribution. Submitted values remain labelled. Cash advances and maintenance are explicitly excluded; no joins to maintenance cost tables. Completed expense originals and trip lifecycle/POD remain unchanged.
- Query safety: bound parameters and explicit sort allowlists. Date bounds require timezones. Bounded list pages. Grouped calculations for all page IDs avoid per-trip N+1 queries. Organization read lock protects multi-query financial consistency.
- Presentation/data exposure: owner financial data is not added to driver trip payloads or offline caches. The UI formats exact strings and never calculates authoritative contribution. React text rendering handles user descriptions/reasons; no raw HTML rendering introduced.
- Audit: created/reviewed/voided/corrected revenue and shared adjustment events carry actor/trip/target/time and safe change metadata. No secrets, signed URLs or binary attachments.

## Tests and residual limits

API/direct PostgreSQL tests cover other-tenant/driver reads, mutation denial, projection/original tampering, restrictive overrides, mass assignment, Decimal attacks, reason/sequence/reversal validation, concurrent identical replay and audit-failure rollback. Golden tests assert original toll/revenue and completed Trip are unchanged after overlays, and linked maintenance cannot affect contribution.

Revenue corrections use the existing owner/admin adjustment capability; there is no two-person approval. Per-record revenue adjustment history is currently unpaginated. Cancelled trips are financial read-only. A completed trip containing previously unreviewed costs stays provisional under the existing expense rules. These are documented scope limits rather than silent accounting assertions.

Physical-device/Safari, Docker, remote CI, staging, production storage/monitoring, remote recovery, deployed isolation/load and independent security review remain UNVERIFIED launch blockers. Existing local Batch 12 recovery is historical evidence; this batch does not claim a revenue-specific remote restore.
