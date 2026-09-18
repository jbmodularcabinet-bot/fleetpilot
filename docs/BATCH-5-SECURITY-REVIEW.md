# Batch 5 security review

Scope: delivery attempts, proof of delivery, private evidence, recipient signatures, exceptions and operator retry/review. Source review and local adversarial verification; not an independent penetration test or a production security certification. Final execution outcomes are in [BATCH-5-REPORT.md](BATCH-5-REPORT.md).

## Authorization and isolation

- Existing authenticated sessions, active organization/membership checks, restrictive capability overrides, Origin protection and transaction-local tenant context are reused. No alternate upload authentication, public URL, token-in-query scheme or client-selected tenant/actor exists.
- Every delivery route enforces a capability. Drivers resolve their own active linked domain profile and assigned trip before reading or writing delivery records. Owner/operator permissions are separate from driver-own permissions. Review and retry authorization are never granted to drivers.
- All four new tables ENABLE and FORCE PostgreSQL RLS. Child visibility depends on the visible parent trip, retaining Batch 4's same-tenant cross-driver restriction. Composite foreign keys bind organization, trip and delivery attempt; signature references also bind the same attempt. Search/list counts use tenant/parent scope and bounded pagination. There is no global driver POD list.
- Known foreign UUID tests cover attempts, POD, photos, signatures, upload, exception creation, review and resolution. Restricted-role direct PostgreSQL tests verify missing-context denial, foreign counts/updates and same-tenant cross-driver invisibility. RLS is not replaced by application filters.
- Runtime database credentials remain a trusted server boundary. Capability-level RBAC remains application-authoritative; RLS independently enforces row ownership. Credentials must never be distributed to clients. The existing API startup rejects superuser/BYPASSRLS runtime roles.

## File boundary

- API retrieval reauthorizes every request against session, tenant, capability and trip ownership. A UUID or filename alone is insufficient. File bytes are returned only after checksum verification, with no-store/nosniff and restrictive response CSP. The frontend requests these private API resources directly rather than sending them to a public image optimizer.
- Local storage is outside web/public directories, with server-generated tenant/random keys and strict path validation. Original filenames cannot supply storage paths, path traversal or header injection. Neither metadata responses nor audits expose object keys or filesystem locations.
- Bounded raw upload bodies reject empty or greater-than-5-MiB inputs. JPEG/PNG/WebP MIME, extension and actual decoded format must agree. Malformed, animated and greater-than-16-megapixel images fail. Normalized pixel-only PNG output strips embedded metadata and appended content. Output size is also bounded. Retained file count is capped at 12 per attempt.
- Pillow is pinned in the API dependency manifest. Validation is image safety handling, not malware certification, legal verification, OCR or automated damage detection. Decoder vulnerabilities, infrastructure rate limits and storage quotas still need production monitoring and patch management.
- Submitted objects are never overwritten. Explicit pre-submission supersession keeps original metadata/bytes and audits the replacement. Closed/failed attempts cannot be uploaded to or superseded. There are no ordinary deletion APIs or database DELETE policies.
- Production object storage is **NOT CONFIGURED / UNVERIFIED**. Production evidence operations fail closed. No public bucket, cloud credential or long-lived signed URL was added.

## Workflow and transaction integrity

- Only the POD command performs the normal DELIVERED transition. Required recipient, photo, driver confirmation and server time are checked, as are stored object availability/checksums. The old bare delivery action is explicitly rejected. Completion of new trips requires reviewed POD.
- Database guards reject an unbacked DELIVERED trip, policy-flag bypass, mutable evidence identity/bytes metadata, historical attempt edits, silent POD edits and rewritten exceptions. A deferred outcome constraint requires matching POD/exception for successful/failed attempts at commit.
- Failed attempts retain their FAILED state, notes, photos and timestamps. Resolution updates only explicit retry fields. New attempts get new numbers and retain all prior evidence. An unresolved exception blocks progress; no silent reset or automatic success is possible.
- Every command uses the existing organization lock and expected trip version. Upload performs permission/ownership checks before consuming bytes, then rechecks authority and refreshes the trip after acquiring the lock. This avoids stale identity-map values during concurrent uploads. Competing submissions, uploads, failures and reviews are conflict-safe rather than last-write-wins.
- Delivery commands explicitly commit before sending success. This closes a discovered timing issue where request-scoped dependency cleanup could otherwise raise an audit/commit error after response start. Fault-injection tests verify POD/attempt/trip/milestone/audit rollback and cleanup of uncommitted upload objects. No successful delivery remains after transaction failure.
- A hard process/power failure can leave a private unreferenced file because local filesystem writes and PostgreSQL are not a distributed transaction. It has no evidence ID that the API can resolve. Orphan cleanup, combined backups and crash recovery are operational prerequisites, not falsely claimed atomic cross-storage guarantees.

## Input, UI and audit safety

- Strict schemas reject mass assignment of tenant, actor, timestamp, status and policy fields. Typed UUIDs/enums and bound SQLAlchemy expressions are used. No arbitrary SQL/filter clauses or filenames are interpolated into queries.
- React renders recipient/note/filename text without raw HTML. Signature capture supports pointer/touch, clearing before upload and explicit confirmation. Signature bytes are validated like any image; no claim of signer identity or legal non-repudiation is made.
- Audits use the existing immutable audit table, with trip/attempt/record IDs and action names. No binary evidence, passwords, tokens, object keys or signed URLs are logged. Review records timestamp/reviewer without changing original POD content.
- Per-role and restrictive-denial tests verify that hiding UI controls is supplemental. Tests also cover unauthenticated retrieval, disallowed Origin, missing/corrupt objects, incorrect content types and executable/path-like filenames.

## Findings and remaining limits

Original implementation verification: 155 backend tests passed, including direct forced-RLS, tenant/cross-driver, file attack, immutability and transaction-failure cases. That original browser run passed all 15 tests with one unchanged rerun after a development-proxy connection reset; the latest locked-v1 rerun passed all 15 in one run without retries. No unresolved Batch 5 security release blocker was identified within this reviewed and tested local scope.

Resolved during implementation: audit failure after response start; stale trip identity-map version during concurrent upload; bare delivery bypass; completion without reviewed POD. Final test/build status is recorded separately and must be consulted before a PASS claim.

No external security assessment, production deployment, large-fleet load/soak test, cloud object-store policy review, fresh online vulnerability assessment, storage quota stress test or database/object backup-restore drill has been performed: **UNVERIFIED**. Existing process-local rate limits, CSP hardening, observability and account lifecycle limitations remain. Local file confidentiality depends on host filesystem access control. This batch supplies no offline queue, background location, notifications, finance or other Batch 6 functionality.


## Locked v1 follow-up review

The follow-up request starts from the already implemented Batch 5 source, not a Batch 4 checkout. Delivery domain/schema, authorization, private storage, transaction boundaries and state-machine protections are retained. The new code is browser verification only; no production API, permission, storage configuration or migration is added or relaxed. All six locked JPEG originals and their manifest remain untouched. The alternate dark profitability concept is not a runtime theme.

The complete backend/security regression passed 155 tests; frontend passed 14; all 15 browser workflows passed in one run with zero retries. All six original asset hashes/sizes/read-only checks passed before and after work. No new unresolved local security release blocker was identified. Final outcomes are recorded in BATCH-5-REPORT.md and BATCH-5-DESIGN-VERIFICATION.md. Existing production limitations remain applicable.
