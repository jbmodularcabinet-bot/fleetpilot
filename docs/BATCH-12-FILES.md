# Batch 12 file inventory

Compared against pre-batch SHA-256 manifest `.runtime/batch12-baseline.json`; Git has no tracked baseline, so untracked does not mean created in this batch. Generated runtime logs/dumps/screenshots are excluded from source inventory.

## Created

- `apps/api/tests/maintenance_recovery.py`
- `apps/api/tests/test_maintenance_concurrency.py`
- `docs/BATCH-12-DESIGN-VERIFICATION.md`
- `docs/BATCH-12-FILES.md`
- `docs/BATCH-12-REPORT.md`
- `docs/BATCH-12-SECURITY-REVIEW.md`
- `docs/RECOVERY-VERIFICATION.md`
- `docs/STAGING-VERIFICATION.md`

## Modified

- `apps/api/tests/hardening_workflow.py`
- `apps/api/tests/verification_load.py`
- `apps/web/public/driver-sync.js`
- `apps/web/src/lib/offline.ts`
- `apps/web/tests/offline.test.ts`
- `docs/DEVICE-VERIFICATION.md`
- `scripts/hardening-drill.py`
- `tests/e2e/expenses.spec.ts`

## Scope

One application logic fix: durable local expense version selection in `offline.ts`, with regenerated `driver-sync.js`. No UI/component/style/token/logo/navigation edits. Test changes add concurrency, stale expense projection/two-tab regression, maintenance recovery and bounded local load checks. Documentation records available and unavailable gates. No dependencies, migrations, infrastructure configuration, secrets or production data changed.
