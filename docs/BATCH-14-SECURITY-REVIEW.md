# Batch 14 internal security review

Scope: cash issuance/adoption, settlement/return/void/reversal, financial review and final contribution gating. This is an engineering review, not an independent assessment. Execution evidence and final status are in BATCH-14-REPORT.md.

## Controls

- IDOR/BOLA: tenant-scoped trip/advance/source lookups and composite tenant/trip references. Known foreign IDs return denial without record data. No public driver advance endpoint. All new tables force PostgreSQL RLS; permitted drivers cannot enumerate advance, settlement or review history.
- RBAC: explicit cash read/create/settle/void and financial read/approve capabilities. Owner/admin approval only; manager/accounting can settle but cannot approve. Dispatcher/driver have no new financial authority. Restrictive overrides and membership/user activity are refreshed under the existing organization lock before writes and replay.
- Mass assignment: strict payload schemas accept no organization, driver, actor, status, outstanding or effective total. Driver derives from assigned trip or captured source. API monetary values are strict decimal strings. Currency is PHP.
- Double counting: cash issuance/application/return/reversal never creates a direct cost. The existing reviewed expense projection is authoritative. Advance category and maintenance remain excluded. Legacy captured advances require explicit adoption and block approval until reconciled.
- Over-settlement/double application: exclusive organization lock, renewed authorization, exact balance and whole effective reviewed expense checks. A database trigger independently enforces eligibility, balance and one active allocation. A unique reversal target prevents multiple credits. No negative balance or silent editing.
- Retry safety: stable actor-scoped UUID receipts committed with domain/history/audit. Matching replay recovers a lost response; changed payload conflicts. The native form retains its key for retry of the same command. Fresh unrelated commands are separately validated against the balance.
- Review bypass: one centralized database readiness policy governs API/calculation/approval trigger. FINAL requires a current APPROVED event and no blockers. Latest-event matching prevents stale approval. Every financial mutation changes the event token, even before first approval. No implicit reapproval after reversals.
- Atomicity: event, source, audit and replay receipt share the transaction. Audit failure rolls back settlement; invalidation of earlier approval is transactional. Financial commands do not reopen trips or change Trip.version/milestones/POD.
- History/audit: advance identity/amount and all settlement/review rows are append-only; database update/delete guards retain history. Reversals are compensating entries. Server actor and timestamps are retained. Audit metadata contains safe financial IDs/amounts/reasons, never passwords, tokens, raw receipts or signed URLs.
- Query/UI: bound SQL parameters, bounded list/choice/history pages, React text rendering, unchanged locked components. Per-advance history is currently returned in full. Existing record-level restrictions protect underlying receipts.

## Findings resolved during implementation

A PostgreSQL trigger record-variable name overlapped a query alias during initial settlement tests; it was renamed and the migration reapplied. A stale-first-approval race was identified during review: no prior approval meant no event token changed. Financial mutations now append a change event before or after initial approval, and an explicit stale-first-approval regression exercises the fix. UI financial approval uses its own confirmation instead of sharing settlement confirmation state.

## Test scope and residual risks

New tests exercise online/partial settlement, exact cents, immutable history, reversal, independent concurrent over-return/application, identical lost-response replay, API/direct database tenant-role denial, restrictive overrides, mass assignment, audit-failure rollback, review blocking and correction invalidation. Check the report for completed full regression/browser results; unexecuted gates are not implied by this review.

Single privileged reviewer is intentional. The server cannot inspect unsent queues on disconnected devices; explicit operator confirmation is required and any later accepted financial record invalidates approval. Completed trips with old unreviewed expenses remain blocked under existing ordinary expense immutability. A dedicated advance amount cannot be silently corrected; existing source corrections must be reconciled explicitly. Per-advance long-history and high-concurrency capacity are unverified. Organization-level serialization favors correctness over concurrency.

Physical Android/Safari, Docker execution, remote CI/staging, production storage/IAM, monitoring, remote recovery, deployed isolation and independent security review remain UNVERIFIED. Future recovery tooling includes new tables, but a Batch 14 recovery drill was not executed. No external launch blocker is waived.
