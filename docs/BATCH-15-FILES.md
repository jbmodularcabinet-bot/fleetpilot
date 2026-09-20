# Batch 15 resumed pass — file manifest

Changes made on 19 September 2026, building on existing committed Batch 15 work. Pre-existing Creative OS capture files are untouched.

## Created
- apps/api/tests/test_transaction_boundary.py — commit-before-response, failed commit and dependency-scope regression tests.
- apps/api/migrations/versions/0013_legacy_review_guards.py — additive role/permission, locking and review-token guards.
- apps/api/tests/governance_recovery.py — acceptance, settlement and approved-total recovery assertions.
- tests/e2e/legacy-review.spec.ts — acceptance, approval, original preservation, reload and design checks.
- docs/BATCH-15-RESUMPTION.md — current execution/evidence report.
- docs/BATCH-15-SECURITY-REVIEW.md — findings, fixes and residual risks.
- docs/BATCH-15-DESIGN-VERIFICATION.md — unchanged product UI and asset checks.
- docs/BATCH-15-FILES.md — this manifest.

## Modified
- apps/api/fleetpilot/auth.py — return dependency service objects; retain function-scoped database lifecycle.
- apps/api/fleetpilot/delivery_routes.py — function-scoped database dependency.
- apps/api/fleetpilot/master_routes.py — function-scoped database dependencies.
- apps/api/fleetpilot/routes.py — function-scoped database dependencies.
- apps/api/fleetpilot/tenancy.py — reuse the function-scoped database dependency.
- apps/api/fleetpilot/trip_routes.py — commit before trip HTTP responses.
- tests/e2e/offline.spec.ts — synchronize worker connectivity; isolate the foreground lost-response injection; bound ECONNRESET retry for a read-only probe.
- apps/api/fleetpilot/governance_routes.py — fuel permission and duplicate acceptance conflict.
- apps/api/fleetpilot/main.py — readiness migration head.
- apps/api/tests/test_legacy_financial_review.py — seven adversarial/regression cases.
- apps/api/tests/e2e_governance.py — opt-in unreviewed browser fixture; existing default preserved.
- apps/api/tests/hardening_workflow.py — governance creation/restored verification.
- scripts/hardening-drill.py — legacy table counts and Batch 15 artifact naming.
- docs/DEPLOYMENT-HARDENING.md — correct current readiness head.
- docs/BATCH-15-REPORT.md — pointer to dated current evidence; historical narrative retained.
- docs/BATCH-15-LOCAL-REGRESSION-FINAL.md — pointer to dated current evidence.

No dependencies, domain originals, visual assets, product frontend or prior migration files were changed. Ignored .runtime contains logs and disposable synthetic recovery artifacts; no secrets were added to tracked files. Browser failure traces can contain synthetic test-session cookies and require restricted local access.
