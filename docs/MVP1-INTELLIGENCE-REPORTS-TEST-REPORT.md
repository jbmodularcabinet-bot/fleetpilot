# MVP1 reporting test evidence

Date: September 20, 2026. This document distinguishes executed demo checks from uncompleted release gates.

## Executed checks

The new 58 unit tests passed. Coverage includes four-trip arithmetic, weighted margin, explicit rounding, negative/N/A behavior, missing-input classification, advance exclusion, thresholds, stable findings, policy/filter validation, actual role sets, restrictive overrides, timezone/DST boundaries, CSV injection cases and print escaping.

The first combined backend run reported 77 passed and 2 failed. Both failures were new fixture setup defects: a driver-only capture endpoint was called while authenticated as owner, and a bulk scheduled-trip fixture omitted required ORM/default fields. The capture fixture was corrected; the bulk fixture now uses the actual Trip model without weakening database guards. The two corrected cases passed in targeted reruns. A full backend run is tracked separately; initial failures are retained, not reclassified.

The 121-trip case proves first-page rows are not used as portfolio totals, verifies all 121 rows in the export and enforces a <=25 SQL statement budget. The concurrent correction case verifies old-state/new-state coherence under the existing organization lock. Other database cases cover all six reports/exports, corrections/reversals, material history, captured versus issued advances, partial settlement, roles/overrides, cross-tenant filters/RLS, audited policy and synthetic/financial-status filters.

Frontend regression: the first run had 53 passed and one unchanged governance test timed out under shared workstation load. With bounded workers and unchanged assertions/timeouts, all original 54 passed. Adding six reporting UI tests produced 60 passed, zero failed. New tests cover server-value formatting, losses/N/A, denied expense access/no fetch, error-not-zero behavior, synthetic/no-store requests and clearing stale organization data.

TypeScript, frontend lint and the production web build passed after replacing synchronous effect state resets with keyed request snapshots.

## Actual browser checks

Local demo: 16 passed, zero failed. Public HTTPS demo: the same 16 workflows passed, zero failed. They are not 32 distinct tests. Workflows cover actual login, dashboard golden totals, negative-contribution/fuel findings, all six report pages plus CSV/print endpoints, capture/issuance distinction, financial-source drill-down, business-scope isolation, actual download button, mobile containment, no unhandled browser errors and anonymous report/export denial.

Initial browser harness failure: the existing Sign in button has no explicit type attribute. The selector was corrected to its accessible name; authentication was not changed to make the test pass. No credentials or login-form screenshots were saved to public evidence.

## Evidence locations

- .runtime/batch16/reporting-unit.xml
- .runtime/batch16/reporting-targeted.xml
- .runtime/batch16/reporting-fixture-fixes.xml
- .runtime/batch16/reporting-orm-fixture.xml
- .runtime/batch16/frontend-tests.log (initial timeout retained)
- .runtime/batch16/frontend-final.log (54 original cases)
- .runtime/batch16/frontend-with-reporting.log (60 cases)
- .runtime/batch16/web-candidate-validation.log
- .runtime/batch16/demo-local-final/result.json
- .runtime/batch16/demo-public/result.json
- .runtime/batch16/demo-public/golden-overview.json
- .runtime/batch16/demo-public/*.png and *.csv
- .runtime/batch16/backend-full.log / backend-full.xml when complete

Full original browser regression, 1,000-trip/10,000-expense load, new Docker app runtime, physical devices, remote CI and production verification must not be inferred from these demo results. The release handoff records their final observed state.

## Full backend checkpoint and public-security supplement

The complete backend invocation finished with 450 passed, 9 skipped and one setup error in 735.63 seconds. All 79 reporting cases passed in that run. The skipped cases require the existing private local S3 test gateway configuration, which had not been carried into the WSL runtime evidence directory. The setup error was Windows access to another pytest temporary directory. The verifier now uses its own explicit temporary directory; the existing ignored S3 test configuration was copied privately without creating a new service or credentials. The ten affected cases are tracked in backend-environment-rerun.xml. Do not call the first invocation a clean full pass.

Six additional public checks passed: Secure/HttpOnly/SameSite session cookie flags; exact-origin enforcement; driver financial-access denial; cross-tenant trip-filter rejection; invalid-session export denial; and the predeclared four-trip responsiveness budget. These supplement, rather than duplicate, the 16 public demo workflows.

Measured public HTTPS responsiveness: 20 requests, concurrency two, four-trip dataset; p50 216.63 ms, p95 507.40 ms, maximum 516.16 ms; maximum response 15,775 bytes. This includes tunnel/network/web/API forwarding. The workstation CPU is Intel Core i5-10300H, eight logical processors, shared with other development workloads. This is not the requested 1,000-trip/10,000-expense benchmark or production capacity evidence.

Native WSL design verification passed all six locked original hash, size and read-only checks. A Windows invocation against the UNC projection failed its Windows-specific readonly-attribute assertion; the native WSL check verifies the Linux-owned source using its applicable permission model.

## Environment rerun completed

All ten affected backend checks passed in 18.22 seconds after applying the existing private S3 test configuration and an explicit owned temporary directory. Across the full invocation and that targeted rerun, all 460 distinct backend cases have an executed pass; no unresolved case remains in that coverage set. The initial 450-pass/9-skip/1-setup-error invocation remains preserved, and a second uninterrupted 460-case local invocation was not run. Application assertions and database/security guards were not weakened.

The synthetic-data disclaimer uses date-independent wording so the fixed September validation period will not later be mislabeled as future deliveries or today's completed deliveries.
