# FleetPilot Batch 15 — resumed implementation and verification

Date: 19 September 2026.

**BATCH 15 STATUS: CONDITIONAL PASS. DESIGN LOCK: PASS.**

Final local release result: **473 distinct passing tests, 0 failed, 0 skipped: 381 backend + 54 frontend + 38 browser.** All original release cases remain present. This pass adds ten backend cases and one browser case to the existing 462-case Batch 15 baseline. Overlapping preliminary/targeted reruns are not counted again. External release gates remain unverified as detailed below.

## Audit: actual source supersedes the stale conversation baseline

The repository already contained Batch 15 legacy acceptance, migration 0012, 371 backend/54 frontend/37 browser cases, Git commits, a GitHub remote and Docker verification. The earlier conversation summary described only Batch 14. No duplicate legacy-review system was built. Earlier statements in BATCH-15-LOCAL-REGRESSION-FINAL.md that no commit/remote/Docker existed are historical and superseded.

Current committed baseline: 912f37ac0ec5a1f81e1f0118b7bbacb3617aa7e8. The actual successful remote Foundation run was inspected: https://github.com/jbmodularcabinet-bot/fleetpilot/actions/runs/35358836602. The main branch requires foundation; enforce_admins is false. Docker engine 29.8.0 is accessible. These facts do not imply CI has tested the new uncommitted fixes.

## Implemented in this pass

- Additive migration 0013_legacy_review_guards: role-restricted reads, permission checks and organization locking for legacy acceptance, and immutable financial-token invalidation on acceptance.
- API enforces fuel.review when accepting fuel; another key against an accepted expense returns 409, while same-key replay remains idempotent.
- Ten backend regression cases (seven legacy and three transaction-boundary cases) and one browser case. Existing tests remain intact; the browser fixture has an opt-in legacy mode while its existing default is unchanged.
- Recovery fixture now creates actual legacy acceptance, cash issuance/return and financial approval records. Restored records and effective totals are verified, rather than only checking empty table counts. The manifest includes the legacy table and expects 32 forced-RLS tables.
- Shared database dependencies now use function scope so commit finishes before HTTP success. Authentication factories return their service objects without redundant generator lifetimes; the session remains managed by the existing database dependency.
- Readiness now requires migration 0013. No ordinary completed-trip editing, reopening, original expense mutation, lifecycle/POD changes or design changes.

## Verification evidence

| Gate | Fresh result | Evidence |
| --- | --- | --- |
| Backend preliminary regression | 378 passed, 0 failed; 710.91 seconds, before transaction-boundary fix | .runtime/batch15-resume-backend.log |
| Transaction/legacy targeted | 16 passed, including all three boundary tests | .runtime/batch15-resume-transaction.log |
| Backend final regression | 381 passed, 0 failed; 978.27 seconds | .runtime/batch15-release-backend.log |
| Targeted governance/legacy | 39 passed, 0 failed; 167.42 seconds | .runtime/batch15-resume-target.log |
| Frontend | 54 passed, 0 failed | .runtime/batch15-resume-frontend.log |
| Production browser first run | 34 passed / 4 failed; investigation and fixes below | .runtime/batch15-resume-browser.log |
| Production browser final | 38 passed, 0 failed, no retries; 8.7 minutes | .runtime/batch15-release-browser.log |
| TypeScript | PASS, including new browser spec | .runtime/batch15-release-typecheck.log |
| Lint | PASS | .runtime/batch15-release-lint.log |
| Production Next.js build | PASS | .runtime/batch15-resume-build.log |
| Ruff / compileall | PASS | executed locally |
| Dependencies | pip check and npm dependency tree PASS | .runtime/batch15-resume-dependencies.log; command output |
| Migration | test forward/rollback to 0012/reapply PASS; development forward PASS | executed sequentially; .runtime/batch15-resume-schema.json |
| Forced RLS | development and test head 0013; 32 tables, all forced | .runtime/batch15-resume-schema.json |
| API / readiness | actual HTTPS startup, readiness, restart and restored startup PASS | recovery drill below |
| Design originals | 6/6 hash/size checks PASS; no product visual source edited | verify-design-assets.py |
| Updated API Docker build | PASS, local image only | .runtime/batch15-release-docker-build.log |

The local API image ID is sha256:e775c259015b2fe93bb8076b8a604e16622db30b5d0fbbd4249cf2dcb8b4bc53. This pass built the updated image; it did not repeat container runtime smoke for this image or publish it to a registry. Earlier container startup evidence remains historical.

## Recovery and controlled load

LOCAL VERIFIED: .runtime/batch15-drill-56dd88ea550c/result.json and load-result.json. Command: DRILL_BATCH9=1 DRILL_BATCH12=1 DRILL_BATCH15=1 with scripts/hardening-drill.py.

The disposable source and restored databases contain one completed trip, three unchanged submitted expenses, three acceptance events, one closed-trip correction, one reviewed revenue, one cash advance/return, 12 review events, 58 audit records and private POD/receipt/maintenance evidence. Original toll remains PHP300; effective toll PHP350. Approved direct costs PHP3,450 and contribution PHP16,550 on PHP20,000 revenue survive restart and restore. Advance PHP5,000 is fully returned and remains SETTLED. Restored sessions are invalidated and evidence is retrieved only through authenticated APIs with checksum checks; anonymous/foreign-tenant access is denied. All 32 RLS tables remain forced.

Controlled local load against the disposable restored API: 540 requests, concurrency 5, zero errors/timeouts; p50 171.08 ms, p95 1951.93 ms, p99 2812.85 ms. This ran on the shared workstation during regression, not dedicated staging, and does not certify production capacity.

## Failures encountered and resolved

The first five-case audit attempt had setup errors because local PostgreSQL was stopped. Starting the existing service completed crash recovery; subsequent targeted and full regressions passed. The first S3 startup failed because Windows lacks the default filesystem xattrs; restarting with the existing metadata sidecar model allowed the complete recovery drill to pass. The unsuccessful drill artifact is retained; no production failure was hidden or counted as success.

The first complete browser run passed 34 and failed four cases. A tenant-B search briefly returned zero for its just-created trip. Both tenants did have the same trip number; a direct installed-FastAPI probe confirmed response was sent before the yielded dependency committed. Function-scoped database cleanup fixes this ordering, including rollback-before-500 on commit failure. The owner golden assertions are unchanged.

Other failures were a reset connection on a read-only diagnostic GET, immediate worker-online assertion during asynchronous connectivity propagation, and a page-route lost-response injection racing automatic worker sync (which bypasses page.route). The harness now bounds ECONNRESET-only retry to two for that diagnostic GET, polls the same worker-online/locks predicate, and disables automatic background registration only inside the dedicated foreground lost-response test. The preceding worker/background-sync case remains enabled. No HTTP error is retried by that transport setting, no business assertion is removed, and no timeout is extended. The complete final 38-case browser run passed continuously, including the unchanged owner golden/search assertions and all three previously failing offline cases. First-run trace artifacts remain in .runtime/batch15-browser-initial. These harness changes are not a claim of physical-device verification.

## Environment gates and limitations

- Remote CI: inspected PASS for committed 912f37a only. New workspace changes are not committed/pushed and remote verification of them is UNVERIFIED.
- Branch required checks: configured; administrator enforcement remains disabled.
- Docker: current engine and updated API image build verified. Updated container runtime, registry-pinned release and scanning UNVERIFIED in this pass.
- Public HTTPS staging, production deployment, remote private object storage/IAM, external monitoring, remote recovery and deployed isolation: UNVERIFIED. Local .env uses local storage and loopback origin; no additional deployment env file exists beyond .env.example.
- Physical Android and actual Safari/iOS: UNVERIFIED. Desktop Chrome and phone-width layout checks are not physical-device evidence.
- Independent security assessment: UNVERIFIED.
- Legacy acceptance is permanent review history, not source editing or a new reversal engine. Existing administrative corrections/voids remain available. Accepted SUBMITTED expenses are not made eligible for ordinary advance expense application; that still requires REVIEWED source status. No automatic trusted-odometer update occurs.
- PHP/Decimal and direct-contribution-only rules persist. No accounting ledger, invoices, AI, GPS or further business module was started.

Files and security details: BATCH-15-FILES.md, BATCH-15-SECURITY-REVIEW.md and BATCH-15-DESIGN-VERIFICATION.md. Pre-existing untracked Creative OS capture scripts were preserved and excluded from the release spec list; all tracked release browser specs plus the new case are included.

## Closure

Eight files created and sixteen modified, listed in BATCH-15-FILES.md. No unresolved local release blocker remains in the executed scope. Design lock, local RLS/RBAC, original financial history, transaction ordering, migration round trip, production web build, API startup/readiness and local recovery are verified.

Recommended next controlled work: review and publish these fixes through the existing protected-branch/CI process, then verify synthetic public HTTPS staging, private remote storage/IAM, monitoring, remote recovery/deployed isolation and physical Android/Safari/iOS. Updated container runtime and registry provenance also need release evidence. Batch 16 has not started; no further business module was added.
