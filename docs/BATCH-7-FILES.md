# Batch 7 file inventory

Compared with pre-change SHA-256 inventory in ignored `.runtime/batch7-baseline.json`. Root package.json is listed separately because the baseline covered project subdirectories. No original artwork was changed.

## Created

- `apps/api/fleetpilot/sync_routes.py`

- `apps/api/migrations/versions/0006_driver_sync.py`

- `apps/api/tests/test_sync.py`

- `apps/web/public/driver-icon.svg`

- `apps/web/public/driver-sync.js`

- `apps/web/public/driver-worker.js`

- `apps/web/src/app/driver-offline/page.tsx`

- `apps/web/src/components/driver-home.tsx`

- `apps/web/src/components/offline-shell.tsx`

- `apps/web/src/components/offline-status.tsx`

- `apps/web/src/lib/offline.ts`

- `apps/web/tests/offline.test.ts`

- `docs/BATCH-7-REPORT.md`

- `docs/BATCH-7-FILES.md`

- `docs/BATCH-7-AUDIT.md`

- `docs/BATCH-7-DESIGN-VERIFICATION.md`

- `docs/BATCH-7-SECURITY-REVIEW.md`

- `docs/IDEMPOTENCY-AND-CONFLICTS.md`

- `docs/OFFLINE-SYNC-ARCHITECTURE.md`

- `docs/PWA-DRIVER-APP.md`

- `scripts/build-driver-worker.mjs`

- `tests/e2e/offline.spec.ts`
- `tests/e2e/offline-session.spec.ts`

## Modified

- `apps/api/fleetpilot/delivery_routes.py`

- `apps/api/fleetpilot/hardening.py`

- `apps/api/fleetpilot/main.py`

- `apps/api/fleetpilot/rate_limits.py`

- `apps/web/src/app/driver/layout.tsx`

- `apps/web/src/app/driver/page.tsx`

- `apps/web/src/app/manifest.ts`

- `apps/web/src/components/delivery.tsx`

- `apps/web/src/components/login.tsx`

- `apps/web/src/components/navigation.tsx`

- `apps/web/src/components/trips.tsx`

- `apps/web/src/lib/client.ts`

- `apps/web/src/proxy.ts`

- `infrastructure/web.Dockerfile`

- `package.json` — regenerate shared service-worker engine before build/dev.

Generated build/test outputs, runtime secrets, local database/storage files and logs are excluded.
