# Batch 14 file inventory

Compared with pre-edit `.runtime/batch14-baseline.json`; generated build/cache files and ignored runtime evidence are excluded.

## Created — 15

- `apps/api/migrations/versions/0011_cash_advance_review.py`
- `apps/api/fleetpilot/governance_models.py`
- `apps/api/fleetpilot/governance_routes.py`
- `apps/api/tests/test_governance.py`
- `apps/api/tests/e2e_governance.py`
- `apps/web/src/components/governance.tsx`
- `apps/web/tests/governance.test.tsx`
- `tests/e2e/governance.spec.ts`
- `docs/BATCH-14-REPORT.md`
- `docs/BATCH-14-FILES.md`
- `docs/BATCH-14-SECURITY-REVIEW.md`
- `docs/BATCH-14-DESIGN-VERIFICATION.md`
- `docs/CASH-ADVANCE-SETTLEMENT.md`
- `docs/TRIP-FINANCIAL-REVIEW.md`
- `docs/PROFITABILITY-FINALIZATION-POLICY.md`

## Modified — 13

- `apps/api/fleetpilot/financial_routes.py`
- `apps/api/fleetpilot/main.py`
- `apps/api/fleetpilot/permissions.py`
- `apps/api/fleetpilot/profitability.py`
- `apps/api/migrations/env.py`
- `apps/api/tests/test_profitability.py`
- `apps/web/src/components/financials.tsx`
- `docs/DEPLOYMENT-HARDENING.md`
- `docs/PROFITABILITY-CALCULATION-RULES.md`
- `docs/TRIP-PROFITABILITY.md`
- `packages/types/index.ts`
- `scripts/hardening-drill.py`
- `tests/e2e/profitability.spec.ts`

The new migration adds only governance tables/functions/triggers and preserves original financial data. Models register these records. Routes reuse existing context/locking/audit/receipts. Profitability now includes centralized explicit-review gating. Frontend additions are contained in the existing financial card. Permission types match backend roles.

The existing backend/browser profitability golden gains explicit approval before its retained FINAL assertion, as required by Batch 14; its money/security assertions remain. Current-policy notices identify which historical Batch 13 FINAL semantics are superseded. Readiness/deployment documentation track the new head. Recovery tooling includes new tables, but no restore is claimed from a static tooling update.

No dependency manifest/lockfile, original asset, shared CSS/token, Owner/Driver shell or navigation changes. Source originals are locked. Evidence: `.runtime/batch14-*.log`, `batch14-schema.json`, and retained screenshots after browser verification.
