# FLEETPILOT BATCH 8 REPORT

Verification date: 17 September 2026. Scope: Fuel, Tolls & Trip Expenses only.

BATCH 8 STATUS: CONDITIONAL PASS — all local implementation gates passed; physical-device and production-environment checks remain UNVERIFIED under the requested conditional-pass rule.

DESIGN LOCK: PASS — original assets, unchanged shared visual foundations and inherited browser design assertions. No redesign.

## Baseline audit and architecture

Read the Batch 7 report and authoritative implementation before editing. Batch 7 is a conditional local verification baseline, not production certification. Existing code had no expense domain. Preserved authentication, tenant context, permission architecture, forced RLS, audit infrastructure, state machine, POD, private storage and the shared offline queue. Older lifecycle documentation does not override Batch 5 evidence-gated delivery.

The isolated test database was at Batch 7 migration 0006. The development database was still at 0005; this discrepancy is recorded rather than assuming the test baseline had been deployed there. Development forward migration result is recorded below.

Added three mapped domain tables: TripExpense, immutable ExpenseRevision, and ExpenseEvidence. Root expenses reference the current revision through a deferred composite foreign key. Vehicle has an internal monotonic highest-reviewed-fuel reading to enforce a trusted lower bound across drivers without exposing another driver's expenses. Existing master odometer remains unchanged. Expense commands reuse Batch 7's receipt table, organization lock and Trip.version; no separate queue or lifecycle is introduced.

## Implemented behavior

| Area | Result |
| --- | --- |
| Fuel | Liters and price are validated decimal strings. Server calculates PHP amount with Decimal ROUND_HALF_UP. Vehicle/driver derive from the trip. |
| Tolls / parking | Explicit categories, occurrence timestamp, amount, vendor/reference/notes and optional receipt. |
| Allowances / operational expenses | Driver allowance, driver cash advance, helper allowance, loading/unloading fees, subcontractor and Other. Other needs notes; subcontractor needs vendor/payee. No payroll or accounting assertion. |
| Money / totals | PostgreSQL NUMERIC and Python Decimal; string API values; BigInt client estimate only. Server sums current non-voided entries across all authorized pages, separately showing reviewed totals and categories. |
| Odometer | Cannot fall below master or highest-ever reviewed fuel reading, including after reassignment. Never silently changes Vehicle.odometer. Corrected/voided high readings remain conservative lower bounds. |
| Owner review | Explicit permission and timestamp/actor/audit. Review cannot silently change the submitted amount. |
| Correction history | Required reason; append immutable revision, preserve original/review metadata and reset review. No generic money PATCH. |
| Void | Required reason, retained evidence/history, explicit VOIDED state, excluded from totals. No ordinary hard delete. |
| Trip summary / vehicle history | Existing Trip Detail expense card and paginated vehicle Fuel history. Real data only; no profit/efficiency analytics. |
| Receipts | Optional JPEG/PNG/WebP, 5 MiB/16MP limits, decoded-format checks and normalization, private authorized retrieval, immutable keys and explicit supersession history. |
| Offline capture / evidence | Existing IndexedDB queue atomically saves command plus dependent receipt Blobs. Saved locally means browser persistence, not server acceptance. Reconnect revalidates assignment, permission and trip state. |
| Idempotency / lost reply | Stable actor-scoped UUID commands, transactional receipts, conflict on changed payload, same result on replay. Browser test deliberately drops a committed response and verifies ALREADY_APPLIED recovery with no duplicate cost. |
| Closed trips | Scheduled, cancelled and completed trips reject expense writes. Read history remains available subject to current authorization. Administrative closed-trip correction is deferred. |

Operational cost totals include advances and unreviewed submissions as explicitly labelled. They are not accounting expense, profitability or revenue.

## Security review

Tenant and cross-driver API attacks and direct restricted-role PostgreSQL tests passed in the full backend suite. All three new tables use forced RLS, tenant/parent composite foreign keys and immutable-history controls. Known expense/receipt UUIDs grant no access. Driver review/correct/void is denied. Privileged operations refresh permissions after locking, including replay.

File attack tests cover executable, empty, oversized, malformed, spoofed MIME/extension, traversal and unauthorized retrieval. Local private S3 receipt integration verifies anonymous denial, checksum, reconciliation, snapshot and restore. Public uploads and exposed storage keys were not introduced.

Review found and fixed a cross-driver odometer blind spot: driver-filtered expense aggregates could miss a previously assigned driver's reading. The internal monotonic vehicle reading closes that gap without weakening RLS or using SECURITY DEFINER. No unresolved local security release blocker was found; an independent assessment remains UNVERIFIED.

## Files and migration

21 created files and 15 modified files, including documentation and the regenerated existing driver worker. Full paths are in [BATCH-8-FILES.md](BATCH-8-FILES.md). Dependency manifests and lockfiles are unchanged.

Migration: `0007_trip_expenses`, parent `0006_driver_sync`. Adds three tables, relevant tenant/trip/vehicle/history indexes, forced RLS, composite foreign keys, immutable/context guards, and reviewed-fuel odometer maintenance. Isolated database forward, downgrade to 0006, reapply and head verification PASS. Development forward migration: PASS, existing 0005 through 0006 to 0007 head; no development rollback or reset. Evidence: `.runtime/batch8-development-migration.log`.

## Executed quality gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Full backend regression | PASS: 246 passed, 0 failed; 428.51 s | `.runtime/batch8-backend-release.log` |
| Frontend unit tests | PASS: 30 passed, 0 failed | `.runtime/batch8-unit-release.log` |
| Full production-browser regression | PASS: 31 passed, 0 failed; 5.2 min | `.runtime/batch8-browser-release.log` |
| TypeScript including E2E types | PASS | `.runtime/batch8-typecheck-release.log` |
| ESLint | PASS | `.runtime/batch8-lint-release.log` |
| Python Ruff | PASS | `.runtime/batch8-python-release.log` |
| Production Next.js build | PASS | `.runtime/batch8-build7.log` |
| Python dependency validation | PASS: pip check | `.runtime/batch8-pip-release.log` |
| Node dependency validation | PASS: npm ls --all --omit=optional | `.runtime/batch8-dependencies-release.log` |
| FastAPI startup and readiness | PASS: production-browser server starts; GET /ready returned 200, status ready | Browser request log |
| Migration round trip | PASS: downgrade 0006, upgrade head, current 0007 | `.runtime/batch8-migration-final.log` |
| Original asset integrity | PASS: 6/6 originals and manifest sizes/hashes | `scripts/verify-design-assets.py` |

**Final full regression: 307 passed, 0 failed (246 backend + 30 frontend + 31 browser).** No skips were used to establish this result.

Added 59 tests: 47 backend, 10 frontend and 2 browser. Existing tests were retained, not skipped or weakened. Earlier development failures were fixed; only final full runs establish the release result. Those fixes include a trigger field guard, stable concurrent-test envelopes, compact oversized-upload test IDs on Windows, accurate empty offline save wording, and context-level interception for a service-worker lost-response test. Windows temporary-directory ACL failures were resolved by using a workspace pytest basetemp; checks were rerun rather than skipped.

## Golden workflows and design

Online expense golden PASS: ACME Logistics Client, TRK-001/ABC-1234, Juan Dela Cruz, dispatched trip, fuel PHP 3,232.61 + toll 350 + parking 100 + driver allowance 500 = PHP 4,182.61. Receipt persists, owner reviews, corrects with retained history, voids and sees the correct remaining total and vehicle fuel history.

Offline expense golden PASS: four expenses/two receipts survive page close and offline reopen. Reconnection with a deliberately lost committed response recovers by idempotent replay. Exactly four server expenses and both receipts remain; total PHP 4,182.61.

Design evidence: `test-results/batch8-owner.png`, `test-results/batch8-driver-offline.png`, inherited locked-design assertions and phone-width workflow coverage. Screenshots inspected; existing cards, typography, navigation and next-action hierarchy retained. A desktop browser rendering a narrow driver shell is not physical-device verification. [BATCH-8-DESIGN-VERIFICATION.md](BATCH-8-DESIGN-VERIFICATION.md) records the scope.

## Known limitations, risks and UNVERIFIED items

- PHP only; operational inputs, no accounting recognition, profitability or reimbursement reconciliation.
- No post-closeout financial correction workflow. Highest reviewed odometer cannot be reduced through ordinary operations; erroneous high readings need future administrative design.
- Receipts are optional and separately acknowledged. A saved expense can exist while its selected receipt is pending. Driver queue persists Blobs; owner retry state lasts only in the open page.
- Browser storage is subject to eviction/device loss and is not encrypted. No guarantee of OS background execution or offline authorization revocation before reconnect.
- Local disk/private local S3 exercised. Remote production provider/IAM/encryption, deployment/TLS, remote CI, physical Android/iPhone, Safari/iOS, load/soak, production backup drills and independent security assessment: UNVERIFIED.
- No distributed database/object-store transaction or automatic orphan cleanup; existing compensation and report-only reconciliation retained.

## Recommended Batch 9 scope

Separately authorize physical-device/Safari and production-provider verification, then decide administrative closed-trip corrections, mistaken odometer correction and evidence retention/quota policy. No Batch 9 work has started. Maintenance, profitability, revenue, invoicing, GPS, AI, payroll and customer portal remain excluded.

## Supporting documents

- [File inventory](BATCH-8-FILES.md)
- [Security review](BATCH-8-SECURITY-REVIEW.md)
- [Design verification](BATCH-8-DESIGN-VERIFICATION.md)
- [Trip expenses](TRIP-EXPENSES.md)
- [Fuel transactions](FUEL-TRANSACTIONS.md)
- [Expense corrections](EXPENSE-CORRECTIONS.md)
- [Offline sync](EXPENSE-OFFLINE-SYNC.md)
- [Baseline audit](BATCH-8-AUDIT.md)
