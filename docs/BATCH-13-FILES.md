# Batch 13 file inventory

Compared with pre-edit SHA-256 manifest `.runtime/batch13-baseline.json`. Repository has no usable committed baseline for a normal Git diff. Counts exclude ignored runtime logs, screenshots, build artifacts and synthetic data.

## Created — 17

- `apps/api/migrations/versions/0010_trip_profitability.py`
- `apps/api/fleetpilot/financial_models.py`
- `apps/api/fleetpilot/profitability.py`
- `apps/api/fleetpilot/financial_routes.py`
- `apps/api/tests/test_profitability.py`
- `apps/api/tests/e2e_profitability.py`
- `apps/api/tests/profitability_performance.py`
- `apps/web/src/components/financials.tsx`
- `apps/web/tests/financials.test.tsx`
- `tests/e2e/profitability.spec.ts`
- `docs/BATCH-13-REPORT.md`
- `docs/BATCH-13-FILES.md`
- `docs/BATCH-13-SECURITY-REVIEW.md`
- `docs/BATCH-13-DESIGN-VERIFICATION.md`
- `docs/TRIP-PROFITABILITY.md`
- `docs/TRIP-REVENUE.md`
- `docs/PROFITABILITY-CALCULATION-RULES.md`

## Modified — 21

- `apps/api/fleetpilot/adjustment_models.py`
- `apps/api/fleetpilot/adjustment_routes.py`
- `apps/api/fleetpilot/db.py` — formatter-only normalization; no intended behavioral change.
- `apps/api/fleetpilot/hardening.py` — formatter-only normalization; no intended behavioral change.
- `apps/api/fleetpilot/main.py`
- `apps/api/fleetpilot/master_models.py` — formatter-only normalization; no intended behavioral change.
- `apps/api/fleetpilot/permissions.py`
- `apps/api/fleetpilot/rate_limits.py` — formatter-only normalization; no intended behavioral change.
- `apps/api/fleetpilot/storage_admin.py` — formatter-only normalization; no intended behavioral change.
- `apps/api/fleetpilot/trip_models.py` — formatter-only normalization; no intended behavioral change.
- `apps/api/migrations/env.py`
- `apps/api/tests/test_delivery.py` — formatter-only normalization; no intended behavioral change.
- `apps/api/tests/test_expenses.py` — formatter-only normalization; no intended behavioral change.
- `apps/api/tests/test_maintenance_security.py` — formatter-only normalization; no intended behavioral change.
- `apps/web/src/app/(owner)/dashboard/page.tsx`
- `apps/web/src/app/(owner)/trips/[[...segments]]/page.tsx`
- `apps/web/src/components/trips.tsx`
- `apps/web/src/lib/money.ts`
- `docs/DEPLOYMENT-HARDENING.md`
- `packages/types/index.ts`
- `scripts/hardening-drill.py`

Migration env registers the new models; readiness tracks 0010; shared adjustments add revenue targets while retaining expense behavior. Permissions/types add owner financial capabilities. Trip Detail and its existing route expose the new section/list; Command Center unavailable-copy is accurate. The existing money formatter supports negative contribution without floating point. The hardening drill now includes the two new tables in its catalog/restore checks, but no new Batch 13 recovery drill was executed; recovery of these tables remains UNVERIFIED.

## Verification artifacts (ignored, local)

`.runtime/batch13-*.log`, `.runtime/batch13-schema.json`, `.runtime/batch13-performance.json`, `.runtime/batch13-screenshots/` and `.runtime/batch13-baseline.json`. Source originals/assets were not replaced. No dependency/lockfile, base CSS/token, shell or navigation-file changes.
