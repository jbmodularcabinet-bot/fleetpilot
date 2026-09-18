# Batch 8 security review

Engineering review of the expense extension; not an independent security assessment. Final executed gates and release status are recorded in BATCH-8-REPORT.md.

| Concern | Control and evidence |
| --- | --- |
| Tenant IDOR/BOLA | Session-derived organization, explicit query predicates, forced RLS on all three tables, composite tenant/parent foreign keys, known-UUID API attacks and direct restricted-role SQL tests. |
| Cross-driver access | Existing active linked Driver and assigned Trip checks, plus root expense driver snapshot RLS. Tests include an unlinked attacker and Pedro with his own linked active trip. Neither can access Juan's expense, Fuel record, receipt or submission endpoints. |
| Privilege escalation | Explicit owner/operator capabilities, driver own-only capabilities, no review/correction/void for drivers; membership/permission refreshed after organization lock, including specific fuel/evidence permissions before replay. |
| Untrusted queue / mass assignment | Extra fields forbidden; IDs/actor/source derive from authenticated context and trip. Organization, driver, vehicle, trip, status and numeric attacks rejected. Offline projection grants no authority. |
| Money integrity | Plain decimal-string contract, bounded positive NUMERIC/Decimal values, server fuel multiplication and ROUND_HALF_UP, database fuel consistency checks, decimal-string response serialization, BigInt presentation estimate. Exact, rounding, repeated-sum and maximum-amount tests. |
| Race / duplicate / lost reply | Existing organization lock + Trip.version; immutable actor/tenant idempotency receipts committed with operation. Identical replay returns the same result; changed payload conflicts; concurrent duplicate/review and permission-revoked replay tested. |
| Historical tampering | Immutable financial revisions; deferred current-revision composite FK; explicit correction reason/actor/time; void history; database update/delete guards; prior review metadata retained in immutable audit before-images. |
| Trip / vehicle mismatch | No client relationship assignment; root insert trigger checks vehicle/driver against actual open dispatched trip. Terminal/scheduled trips reject writes in service and database. Trip state machine itself unchanged. |
| Odometer | Block below greater of master reading/highest retained reviewed fuel reading; no vehicle odometer overwrite. Serialized submission/review/correction validation; tests verify original master reading retained and a new assigned driver blocked below another driver's reviewed reading without expense-history leakage. |
| Unsafe filters / SQL injection | SQLAlchemy bound parameters for values, static server-owned SQL fragments, validated UUIDs and bounded pagination; no arbitrary sort/column strings or client totals. |
| Public upload / UUID possession | Authorized application byte retrieval only, no public mount or signed URL. Tenant/trip/driver and receipt capability checked before retrieval and upload streaming. Real private S3 anonymous access denied in receipt integration test. |
| File content / path traversal | Existing 5 MiB/16MP image validator, extension/MIME/decoded-format matching, single-frame normalization to PNG, random opaque keys, safe filenames, no user-selected storage destination. Executable, spoofed, malformed, empty, oversized and traversal cases tested. |
| Evidence overwrite | Existing immutable storage put, new metadata/key for each upload, explicit same-expense active supersession, original retained and retrievable. No ordinary delete endpoint. |
| Partial failure | Existing compensating cleanup; creation/receipt audit failures roll back metadata/command receipt. Separate selected receipt is not acknowledged until uploaded. Hard-crash orphan possibility retained and documented. |
| Backup/reconciliation | Shared operator metadata query includes delivery and expense receipts. Real local S3 receipt snapshot/restore/checksum/private retrieval test passed. No production backup certification inferred. |
| Session / CSRF / abuse | Existing opaque HttpOnly sessions, tenant selection, exact-origin mutation checks, nonce CSP, private no-store retrieval and shared rate limits retained. New upload/retrieval paths use existing limits. |
| Secrets | No binary evidence, credentials or URLs in audit. Allowlisted financial metadata only; private object keys omitted from API projections. No credential committed or new external integration added. |

The review identified and fixed a cross-driver odometer blind spot: an aggregate over driver-filtered expense rows could miss another driver's trusted reading. The internal monotonic vehicle reading and reassignment regression close it without bypassing RLS or adding a security-definer function.

## Residual risks and conservative boundaries

Operational cost summaries include unreviewed submissions and advances by explicit label; they are not accounting balances. Odometer history is conservative rather than a correction/scheduling engine. All corrections require an open trip; no administrative post-closeout route is added.

Offline browser storage remains unencrypted and subject to eviction/device loss/XSS. Revocation is detected only on reconnect. No guarantee of OS background execution. Owner selected-receipt retry state is held in the current page; closing that page after expense acceptance but before optional receipt upload may require reopening the expense online. Driver saved queue records are durable within browser storage.

No cross-system distributed transaction, automatic orphan deletion, retention/quota policy or production capacity claim. Remote provider IAM/encryption, deployment/TLS, remote CI, physical Android/iPhone, Safari, load/soak and independent assessment remain UNVERIFIED. Local tests are not production certification.

Final local verification: full 246 backend, 30 frontend and 31 production-Chrome browser tests passed (307 total, zero failed). Forced-RLS/API isolation, file attacks, real private local S3 restore, concurrency and lost-response golden checks are included. Engineering review result: no unresolved local release blocker; overall CONDITIONAL PASS for unverified external/device/production gates.
