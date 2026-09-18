# Batch 12 security review

17 September 2026. Scope: verification and one minimal offline queue fix; application security architecture is unchanged. Final execution results are in BATCH-12-REPORT.md.

## Review

Reviewed tenant/driver ownership enforcement, forced PostgreSQL RLS, maintenance availability locks, immutable history, private evidence authorization/storage validation, durable replay receipts, session/logout isolation, worker/IndexedDB persistence, production configuration, HTTP headers/cookies and recovery tooling.

The added concurrency tests use independent authenticated operators and competing dispatch/maintenance requests. They assert that completing one of two downtime work orders cannot clear the other blocker, and that dispatch and maintenance start cannot both succeed. No weaker transition rule or exception was introduced.

Recovery extends the existing private S3-compatible drill with original defects, images, schedules, completed work, immutable costs, maintenance events and durable command receipts. It verifies original PHP 3,450 trip expenses remain separate from PHP 12,000 maintenance costs. Restored commands replay the original result without creating another defect. File bytes are checked against stored SHA-256 values; unauthenticated and foreign-tenant requests must fail. Driver work-order management remains denied.

The drill creates randomly named disposable databases and buckets, stops the writer before taking a coherent database/object snapshot, checks restored table counts, reconciles object metadata/checksums and invalidates restored sessions before fresh login. Existing databases and buckets are not overwritten or deleted. Synthetic dumps, keys and state stay under ignored `.runtime`; these artifacts still warrant restricted access and retention controls.

Local HTTPS checks require Secure/HttpOnly/SameSite=Lax authentication cookies and security response headers. A self-signed loopback certificate and disabled client certificate-chain check do not verify a public deployment certificate. Existing source-reviewed Docker/CI files do not demonstrate execution.

## Limitations

Physical-device persistence, real OS storage eviction, Safari, remote IAM, deployed isolation, public HTTPS, external monitoring delivery, remote recovery and staging capacity remain UNVERIFIED. Browser emulation and synthetic quota/session tests are explicitly local evidence. This review is not an independent penetration assessment.

No authentication, permission, RLS, upload, lifecycle, financial-history or UI rule was changed for this batch. Any executed failure and its resolution must be recorded in the final report; unavailable targets cannot receive PASS.

## Offline expense conflict fix

The first browser run found a second expense rejected because React props lagged the previously saved expense/receipt versions. Queueing now reads existing owner-scoped durable commands before selecting its next version. Atomic IndexedDB conflict/quota checks and server optimistic versions remain in force. Unresolved FAILED/CONFLICTED commands are not bypassed; originals and idempotency keys are not rewritten. This is a local version-selection fix, not a server conflict auto-resolution policy. Regression results, including the initial failure, are recorded in the report.

## Final outcome

LOCAL PASS after the documented offline version fix: 310 backend, 43 frontend and 35 browser cases passed. No unresolved executed local security blocker. New concurrency tests and real local HTTPS/S3 restart/restore checks passed. Deployed/physical verification and an independent security assessment remain UNVERIFIED. No test was removed, skipped or weakened.
