# Batch 6 file inventory

Compared against pre-change SHA-256 inventory `.runtime/batch6-baseline.json`. Git remains an unborn/untracked repository; no commit or remote diff is claimed. Runtime secrets, downloaded tools, disposable backups, generated caches/build/browser output and dependency installations are excluded. The root browser-test directory was outside the initial inventory; the new hardening.spec.ts is recorded from its explicit creation, and no existing browser test was edited.

Created: 23. Modified: 14. Deleted: 0.

## Created

- `apps/api/fleetpilot/hardening.py`
- `apps/api/fleetpilot/rate_limits.py`
- `apps/api/fleetpilot/s3_storage.py`
- `apps/api/fleetpilot/storage_admin.py`
- `apps/api/migrations/versions/0005_operational_hardening.py`
- `apps/api/tests/hardening_workflow.py`
- `apps/api/tests/reset_e2e.py`
- `apps/api/tests/test_hardening.py`
- `apps/web/src/proxy.ts`
- `docs/BACKUP-RESTORE.md`
- `docs/BATCH-6-DESIGN-VERIFICATION.md`
- `docs/BATCH-6-FILES.md`
- `docs/BATCH-6-REPORT.md`
- `docs/BATCH-6-SECURITY-REVIEW.md`
- `docs/DEPLOYMENT-HARDENING.md`
- `docs/PRODUCTION-STORAGE.md`
- `docs/STORAGE-RECONCILIATION.md`
- `infrastructure/nginx.conf`
- `infrastructure/production.compose.yaml`
- `infrastructure/web.Dockerfile`
- `scripts/hardening-drill.py`
- `scripts/start-production-web.mjs`

- `tests/e2e/hardening.spec.ts`

## Modified

- `.env.example`
- `.github/workflows/foundation.yml`
- `apps/api/fleetpilot/config.py`
- `apps/api/fleetpilot/db.py`
- `apps/api/fleetpilot/evidence_storage.py`
- `apps/api/fleetpilot/main.py`
- `apps/api/requirements.in`
- `apps/api/requirements.txt`
- `apps/api/tests/conftest.py`
- `apps/web/next.config.ts`
- `apps/web/src/components/delivery.tsx`
- `apps/web/tests/delivery.test.tsx`
- `apps/web/src/app/layout.tsx`
- `playwright.config.ts`

## Preserved

All six locked JPEG originals, the manifest, logo, token CSS, global styles, navigation, master data, trips, domain models, existing four migrations, RBAC and RLS policies are unchanged. The delivery component adds only image failure/retry using existing styles, with one new component test. Existing tests retain their assertions; conftest only resets the new development memory-limit windows. No Batch 7 module.

Migration: 0005_operational_hardening. New runtime dependency: pinned boto3 and required transitive packages. No Node dependency or lockfile change.
