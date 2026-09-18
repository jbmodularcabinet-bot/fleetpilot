# Batch 3 file inventory

Compared with the SHA-256 baseline captured before Batch 3 edits. Generated caches, runtime credentials, database files, screenshots and test reports are excluded.

## Created — 16 files

| File                                                               | Responsibility                                                                     |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| `apps/api/fleetpilot/master_models.py`                             | Tenant master models, composite references, constraints and indexes                |
| `apps/api/fleetpilot/master_schemas.py`                            | Strict validated input/output schemas                                              |
| `apps/api/fleetpilot/master_routes.py`                             | Authorized CRUD, search, status actions, assignment lifecycle and driver self-view |
| `apps/api/migrations/versions/0002_fleet_master.py`                | Forward/rollback schema, forced RLS and immutable assignment history               |
| `apps/api/tests/test_master_data.py`                               | 33 backend domain/security/database test cases                                     |
| `apps/api/tests/e2e_setup.py`                                      | Test-only fresh organization/owner provisioning                                    |
| `apps/web/src/app/(owner)/customers/[[...segments]]/page.tsx`      | Customer list/create/detail/edit routes                                            |
| `apps/web/src/app/(owner)/fleet/[domain]/[[...segments]]/page.tsx` | Vehicle/driver list/create/detail/edit routes                                      |
| `apps/web/src/components/master-page.tsx`                          | Server-side route/permission dispatch                                              |
| `apps/web/src/components/master-data.tsx`                          | Lists, forms, details, assignments, audit and own driver view                      |
| `apps/web/src/lib/master-data.ts`                                  | Domain field configuration, DTOs and allowlisted form payloads                     |
| `apps/web/tests/master-data.test.ts`                               | Three frontend serialization/profile checks                                        |
| `tests/e2e/master-data.spec.ts`                                    | Golden CRUD/assignment/isolation workflow and UI state/responsive scenario         |
| `docs/BATCH-3-REPORT.md`                                           | Implementation, results, limitations and exit decision                             |
| `docs/BATCH-3-FILES.md`                                            | This inventory                                                                     |
| `docs/BATCH-3-SECURITY-REVIEW.md`                                  | Threat review, role matrix, controls and residual risks                            |

## Modified — 10 files

| File                                       | Change                                                                            |
| ------------------------------------------ | --------------------------------------------------------------------------------- |
| `README.md`                                | Current Batch 3 scope, usage, API semantics and migration guidance                |
| `apps/api/fleetpilot/main.py`              | Registers master-data router                                                      |
| `apps/api/fleetpilot/permissions.py`       | Explicit resource/assignment permissions and conservative role grants             |
| `apps/api/fleetpilot/routes.py`            | Tenant-scoped entity audit filtering, assignment correlation and actor/entity IDs |
| `apps/api/migrations/env.py`               | Registers master models in Alembic metadata                                       |
| `apps/web/src/app/driver/profile/page.tsx` | Shows own linked driver profile/current vehicle                                   |
| `apps/web/src/app/globals.css`             | Responsive master-data styles using existing tokens                               |
| `apps/web/src/components/navigation.tsx`   | Enables permission-aware Customers/Vehicle/Driver navigation                      |
| `apps/web/vitest.config.ts`                | Includes `.test.ts` cases and uses one worker                                     |
| `packages/types/index.ts`                  | Extends shared Permission union                                                   |

## Preserved

Phase 0 audit and Batch 2 report/file inventory; initial migration; authentication/session architecture; database/transaction handling; audit immutability; existing tests; approved visual tokens and brand; dependency manifests/lockfiles. No existing application file was deleted.
