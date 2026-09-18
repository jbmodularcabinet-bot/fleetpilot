# Batch 11 file inventory

Compared with the pre-batch SHA-256 manifest in .runtime/batch11-baseline.json. The repository has no baseline Git commit; existing files are preserved, with changes identified by content hashes. Runtime logs, build/cache outputs and private environment files are excluded.

Root configuration files were already present and were not modified; the pre-batch manifest covers the application/package/script/test/document trees.

## Created (20)

- `apps/api/fleetpilot/maintenance_models.py`
- `apps/api/fleetpilot/maintenance_routes.py`
- `apps/api/fleetpilot/maintenance_schemas.py`
- `apps/api/migrations/versions/0009_maintenance.py`
- `apps/api/tests/test_maintenance.py`
- `apps/api/tests/test_maintenance_security.py`
- `apps/web/src/app/(owner)/maintenance/page.tsx`
- `apps/web/src/app/(owner)/maintenance/work-orders/[id]/page.tsx`
- `apps/web/src/components/maintenance.tsx`
- `apps/web/tests/maintenance.test.tsx`
- `docs/BATCH-11-DESIGN-VERIFICATION.md`
- `docs/BATCH-11-FILES.md`
- `docs/BATCH-11-REPORT.md`
- `docs/BATCH-11-SECURITY-REVIEW.md`
- `docs/DRIVER-DEFECT-REPORTING.md`
- `docs/MAINTENANCE-COSTS.md`
- `docs/MAINTENANCE-SCHEDULES.md`
- `docs/MAINTENANCE-WORK-ORDERS.md`
- `docs/VEHICLE-DOWNTIME.md`
- `tests/e2e/maintenance.spec.ts`

## Modified (21)

- `apps/api/fleetpilot/hardening.py`
- `apps/api/fleetpilot/main.py`
- `apps/api/fleetpilot/master_models.py`
- `apps/api/fleetpilot/master_routes.py`
- `apps/api/fleetpilot/master_schemas.py`
- `apps/api/fleetpilot/permissions.py`
- `apps/api/fleetpilot/storage_admin.py`
- `apps/api/fleetpilot/trip_routes.py`
- `apps/api/migrations/env.py`
- `apps/web/public/driver-sync.js`
- `apps/web/src/components/driver-home.tsx`
- `apps/web/src/components/master-data.tsx`
- `apps/web/src/components/offline-status.tsx`
- `apps/web/src/components/trips.tsx`
- `apps/web/src/lib/client.ts`
- `apps/web/src/lib/master-data.ts`
- `apps/web/src/lib/offline.ts`
- `packages/types/index.ts`
- `docs/DEPLOYMENT-HARDENING.md`
- `scripts/hardening-drill.py`
- `tests/e2e/design-v1.ts`

Generated driver-sync.js is rebuilt from the existing offline worker source. No dependency manifest/lockfile, design asset, global CSS, navigation component or font was changed. No secrets added.
