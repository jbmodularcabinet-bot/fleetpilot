# Batch 9 security review

Engineering review, not an independent penetration assessment. Final executed results are in BATCH-9-REPORT.md.

| Concern | Control |
| --- | --- |
| Completed-trip bypass | Separate event and effective projection; existing trip, expense/revision/evidence triggers unchanged. No reopen or ordinary-field bypass. |
| IDOR / tenant manipulation | Tenant comes from session; target belongs to the requested trip; composite foreign keys and forced RLS on both tables. UUIDs are validated; missing foreign rows return 404. |
| Role escalation | Only OWNER/ADMIN defaults; restrictive deny overrides; server checks, refreshed under organization lock. Trigger independently checks actor/role/denied capability. Driver cannot read privileged history or write adjustments. |
| Projection tampering | No generic update API; database trigger permits projection writes only from the adjustment trigger. Immutable event trigger rejects UPDATE/DELETE; no history UPDATE/DELETE RLS policy. |
| Money | Strict decimal strings, positive bounded effective amounts, centavo precision, server-computed delta, NUMERIC projection and server aggregation. No float math. |
| Reversal / concurrency | Organization serialization, expected expense sequence, unique per-expense sequence and reversal target, latest-active-first reversal, existing atomic idempotency receipts. |
| Partial failure | Projection/event/audit/receipt share one transaction; audit failure test verifies complete rollback. |
| Unsafe input | Fixed correction types/fields, forbidden extra keys, bound SQL values, no arbitrary categories or source identity changes. |
| Sensitive data | Safe audit fields only. No storage key, credentials, raw receipt or session token in adjustment responses. |
| Odometer | Historical correction only; no automatic vehicle lower-bound reconciliation. |
| Existing systems | Session/CSRF, storage authorization, offline queue and trip state machine preserved and included in full regression. |

The narrow policy defers category corrections, post-cancellation adjustments, revival of ordinary voids, two-person approval and trusted-vehicle odometer reconciliation. A trusted administrator can intentionally change an effective amount; attribution, reason, confirmation and reversibility provide accountability, not accounting/legal certification.

Environment-dependent security (remote IAM/TLS/deployment, external monitoring, device storage and independent assessment) remains UNVERIFIED where unavailable. Local HTTPS/S3 and disposable restore/load results must not be represented as remote production evidence.

Final result: local security/financial release gates PASS within CONDITIONAL PASS overall. 269 distinct backend tests, 36 frontend tests and 32 final production-browser tests passed (337 total, zero failed); final round-trip migration, local HTTPS/S3 restore and 120-request controlled load also passed. No unresolved release blocker in tested scope. External assessment remains UNVERIFIED.
