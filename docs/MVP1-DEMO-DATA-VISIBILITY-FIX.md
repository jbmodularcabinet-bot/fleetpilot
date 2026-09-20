# MVP1 sample-data visibility fix — 2026-09-20

Starting candidate: `82d5ea5d81677339a4de01897801227e1fc2732a`.
The reported empty Intelligence/Reports view was reproduced through the public browser.
Bare pages selected business records for September 1–20; the four sample trips are scheduled September 21–24 and excluded from business metrics.
The retained sample API reconciled to revenue 74000.00, direct cost 40250.00, contribution 33750.00, weighted margin 45.61; no source data was missing.

## Scoped correction
- Add an authenticated, tenant-locked, no-store demo-context read for the explicitly configured local demonstration tenant.
- Derive sample dates and count from actual scheduled pickup records; do not hard-code monetary totals or recreate any trips.
- Bare Dashboard, Intelligence and report routes use these sample filters automatically.
- Explicit business, date, customer, vehicle, lifecycle and financial-status selections are not overwritten.
- Other tenants and production do not acquire automatic sample defaults.
- Missing configured records generate an actionable error, not fabricated zero values.
- Preserve the synthetic-data banner, financial terminology, all existing financial calculations, date records, permissions and source history.

## Verification before demo rollout
Backend reporting + new demo-context suite: 85 passed, 0 failed, 0 skipped.
Frontend suite: 75 passed, 0 failed, 0 skipped.
TypeScript, lint and production web build: PASS.
Early test failures were a test-case TypeScript union, Vitest resolution of Next's server-only marker, and an exact banner-label assertion; each was corrected without dropping assertions or changing runtime permissions.
Native Next server-only protection remains active; only Vitest resolves the framework marker to the framework's bundled server marker.
Public before-fix audit: `.runtime/batch16/entry-audit-before/entry-audit.json`.
Post-rollout evidence belongs in `.runtime/batch16/demo-defaults-public/` and `.runtime/batch16/demo-entry-regression-public/`.
Publishing and live demo verification are separate gates; this pre-rollout document does not claim they have passed.
Production promotion remains blocked pending the complete release gates.
