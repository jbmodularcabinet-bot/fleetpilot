# FLEETPILOT BATCH 12 REPORT

Verification date: 17 September 2026.

BATCH 12 STATUS: CONDITIONAL PASS — all local release gates pass; inaccessible device/remote targets remain UNVERIFIED.

DESIGN LOCK: PASS — no visual changes; six original assets verified.

## Audit and scope

Audited Batch 11 source/reports, maintenance/domain models, expense/correction history, permissions/RLS, private evidence/recovery, offline queue/worker/session behavior, production configuration/health/readiness, CI/Docker files and accessible targets. The baseline agrees with 383 cases: 308 backend, 41 frontend, 34 browser. No existing test was removed, skipped or weakened.

Local PostgreSQL, desktop Chrome and a running private loopback S3-compatible gateway are available. No accessible physical Android/Apple/Safari harness, Docker executable, Git remote/remote CI, HTTPS staging, remote storage/monitoring or remote restore target was found. Source-reviewed infrastructure files do not establish execution. See STAGING-VERIFICATION.md and DEVICE-VERIFICATION.md.

The proposed physical golden sequence conflicts with verified Batch 11 behavior: downtime cannot begin while an operational trip is active. The local recovery fixture closes the trip before maintenance and uses current fleet assignment for a vehicle-only defect. This preserves the safety rule. The exact physical Android/staging sequence remains UNVERIFIED, not substituted by a desktop claim.

## Changes

Added two concurrency tests, maintenance recovery fixtures, local HTTPS header/cookie assertions, restored RLS checks and bounded local load coverage. One minimal offline reliability fix reads durable pending expense/receipt versions before queueing the next expense; atomic collision and quota checks remain unchanged. No visual changes, business features, dependencies or migrations.

Concurrency checks cover two operators starting separate work orders, completing one while the other remains a blocker, and dispatch racing maintenance start. Recovery covers trip/POD/photo/signature/fuel/receipt/toll/parking/adjustment plus defect/photo/schedule/work/cost/maintenance receipt and durable replay receipts. The load helper adds maintenance list, vehicle detail and authorized evidence retrieval to existing login/trip/dispatch/expense/fuel routes.

## Executed failure and root-cause fix

The initial browser run passed 33/34 and failed the second offline expense save with the explicit Not saved conflict banner. The first expense/receipt remained durable; the next form retained stale trip-version props during asynchronous refresh. Expense queueing now projects the existing owner-scoped durable queue before choosing its version, retaining atomic concurrent-writer/conflict and quota rejection. Added stale-projection/conflict unit checks and a two-tab browser regression. The original failing test remains unchanged. Full regression is rerun after this fix; initial failure is not erased or counted as a pass.

## Local quality gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Initial baseline backend | 308 passed, 0 failed; 521.28 seconds | `.runtime/batch12-backend.log` |
| Full backend after fix | 310 passed, 0 failed; 426.75 seconds | `.runtime/batch12-backend-release.log` |
| New concurrency | 2 passed, 0 failed; 3.11 seconds | `.runtime/batch12-concurrency.log` |
| Frontend, after fix | 43 passed, 0 failed | `.runtime/batch12-frontend-release.log` |
| Initial browser | 33 passed / 1 failed; root cause and fix documented above | `.runtime/batch12-browser.log` |
| Final browser | 35 passed, 0 failed, no retries; 5.6 minutes | `.runtime/batch12-browser-release.log` |
| TypeScript | PASS | `.runtime/batch12-typecheck-release.log` |
| Lint | PASS | `.runtime/batch12-lint-release.log` |
| Python | Ruff/compileall PASS | `.runtime/batch12-python.log`; compileall exit 0 |
| Dependencies | pip check/npm dependency tree PASS | `.runtime/batch12-pip.log`, `.runtime/batch12-dependencies.log` |
| Production Next.js build | PASS | `.runtime/batch12-build-release.log` |
| Migration state | Development/test `0009_maintenance`, 26 RLS tables all forced | `.runtime/batch12-schema.json` |
| Design originals | 6/6 PASS | `.runtime/batch12-assets.log` |
| API / health / readiness | LOCAL PASS, real HTTPS API before restart and after restore | `.runtime/batch12-recovery.log` |
| Local recovery | PASS: database + five objects, checksums, counts, 26 forced RLS tables | RECOVERY-VERIFICATION.md |
| Local load | 540 requests, concurrency 5; 0 errors/timeouts; p50 120.03 / p95 420.51 / p99 703.39 ms | `.runtime/batch12-drill-4a24c4c3ed97/load-result.json` |

No new migration was warranted. Prior rollback/reapply is historical Batch 11 evidence; Batch 12 checks current catalogs and fresh migration/restore without downgrading development data. Dependency validation is not a fresh vulnerability-feed audit.

**Final distinct automated result: 388 passed, 0 failed, 0 skipped = 310 backend + 43 frontend + 35 browser.** This preserves the 383-case baseline and adds five tests. Initial browser execution had one failure, fixed as documented; repeat executions and the supplemental HTTPS/recovery/load assertions are not inflated into the unique test count. All local suites were rerun after the application fix.

## External/device outcomes

All physical Android installation, offline force-kill/reopen, camera/POD/signature, expense/defect sync, account switching, session expiry, worker updates and OS storage pressure: **UNVERIFIED**. Actual Safari/iOS: **UNVERIFIED**. Desktop queue/Blob/replay/update/session/quota tests are local evidence only.

Docker execution, remote CI, public HTTPS staging, remote object storage/IAM, external monitoring, remote backup/restore, deployed tenant/cross-driver isolation and staging load: **UNVERIFIED / unavailable**. Local results cannot certify them.

## Security and limits

See BATCH-12-SECURITY-REVIEW.md. No authorization, history, financial or lifecycle rule changed. Local HTTPS uses a self-signed certificate and disabled client chain validation solely in the loopback fixture. Production deployment remains unverified. Ignored local recovery artifacts require restricted access and retention controls.

Browser storage is evictable; unsynced device loss is not recoverable from server backup. OS/browser execution limits background sync. Active-trip emergency downtime requires a future explicit workflow decision; this batch does not bypass the blocker. Existing PHP-only costs and conservative conflict handling remain unchanged.

Recommended Batch 13: complete unavailable physical-device/staging/storage/monitoring/recovery gates in a controlled environment, then reassess readiness. No business module or Batch 13 starts automatically.

## Workflow and security outcomes

Maintenance concurrency: PASS, including distinct operator actors and dispatch/start exclusion. Local recovery golden: PASS through POD/review/completion, +50 adjustment, vehicle-only defect/repair/schedule/cost/evidence and restored replay. Physical combined golden: UNVERIFIED and its active-trip/downtime order conflicts with the verified blocker. Restore replay: PASS, original defect ID and ALREADY_APPLIED retained. Browser lost-response expense replay: PASS on final source, including the originally failing test and the new two-tab case.

Private evidence: LOCAL PASS; authorized hash-verified downloads and anonymous/foreign tenant denials. Cookie/auth security and response headers: LOCAL HTTPS PASS; no public-certificate/deployed-proxy claim. Maintenance cost remains PHP 12,000 separate from effective trip expenses PHP 3,450. Backup/restore data remains local only. Monitoring is not configured. The load run shared the workstation with backend regression; its timing is supplementary, not capacity certification.

Files: eight created and eight modified, enumerated in BATCH-12-FILES.md. Migrations: none. Design evidence: BATCH-12-DESIGN-VERIFICATION.md. Security findings and scope: BATCH-12-SECURITY-REVIEW.md. Device availability: DEVICE-VERIFICATION.md. External gate matrix: STAGING-VERIFICATION.md. Recovery dataset and route latency details: RECOVERY-VERIFICATION.md.
