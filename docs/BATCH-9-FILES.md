# Batch 9 file inventory

Compared against pre-edit SHA-256 manifest `.runtime/batch9-baseline.json`; no Git commit baseline exists. Runtime logs, test screenshots, dump/object snapshots, caches and build output are ignored verification artifacts, not source deliverables.

## Created (16)

- `apps/api/fleetpilot/adjustment_models.py`
- `apps/api/fleetpilot/adjustment_routes.py`
- `apps/api/migrations/versions/0008_closed_trip_adjustments.py`
- `apps/api/tests/test_adjustment_security.py`
- `apps/api/tests/test_adjustments.py`
- `apps/api/tests/verification_load.py`
- `apps/web/src/components/adjustments.tsx`
- `apps/web/tests/adjustments.test.tsx`
- `docs/BATCH-9-DESIGN-VERIFICATION.md`
- `docs/BATCH-9-FILES.md`
- `docs/BATCH-9-REPORT.md`
- `docs/BATCH-9-SECURITY-REVIEW.md`
- `docs/CLOSED-TRIP-ADJUSTMENTS.md`
- `docs/LOAD-TEST-REPORT.md`
- `docs/PRODUCTION-VERIFICATION.md`
- `tests/e2e/adjustments.spec.ts`

## Modified (11)

- `apps/api/fleetpilot/expense_routes.py`
- `apps/api/fleetpilot/main.py`
- `apps/api/fleetpilot/permissions.py`
- `apps/api/migrations/env.py`
- `apps/api/tests/hardening_workflow.py`
- `apps/web/src/components/expenses.tsx`
- `docs/EXPENSE-CORRECTIONS.md`
- `docs/FUEL-TRANSACTIONS.md`
- `docs/TRIP-LIFECYCLE.md`
- `packages/types/index.ts`
- `scripts/hardening-drill.py`

## Notes

No files deleted. No dependency manifests or lockfiles changed. Existing test cases are retained; the existing disposable hardening workflow gains an opt-in Batch 9 expense/adjustment verification path and the drill includes expense evidence and new table restore checks. Shared UI tokens/primitives, global styles, primary navigation, POD component, offline engine and six original design references are unchanged. Historical domain docs receive an explicit Batch 9 addendum rather than silently redefining older lifecycle behavior.
