# Hosted backend source baseline

The deployment branch starts at `9f73cea168a8c6a13b5ffc3a191bc50f967cd0b8`, preserving both existing local UI/reporting commits. It adds only the backend hardening required to deploy the current canonical implementation. The original working tree is not modified.

## Selected source

- `0013_legacy_review_guards.py`: tightens legacy-review read RLS, checks current role and restrictive permissions under the organization lock, and invalidates the financial review token after acceptance. Downgrade removes the new triggers/function and restores the prior read policy without deleting business records.
- `governance_routes.py`: enforces fuel review permission and returns a conflict for duplicate acceptance while preserving same-key idempotency.
- `main.py`: readiness expects migration 0013.
- `auth.py`, `tenancy.py`, `routes.py`, `master_routes.py`, `trip_routes.py`, `delivery_routes.py`: shared database dependency uses function scope so commit/rollback completes before response bytes. Authentication factories return service objects while database lifetime remains managed by the dependency.
- `test_legacy_financial_review.py` and `test_transaction_boundary.py`: regression coverage for RLS, restrictive permissions, stale review tokens, duplicate acceptance, and success/error transaction ordering.

Existing 0012 and earlier migrations provide all referenced tables, functions, permissions and application models. The graph must have exactly one head, 0013_legacy_review_guards.

## Excluded local work

Browser fixtures, UI/offline tests, recovery-drill extensions and historical release reports are outside this deployment-source selection. No Finance integration, quote domain, Sites bridge, UI changes or production credentials are added.

## Production prerequisites

Use a dedicated FleetPilot PostgreSQL database, a restricted NOSUPERUSER/NOBYPASSRLS runtime role, separate operator/migration credentials, PostgreSQL rate limiting and private HTTPS S3-compatible storage. Existing production startup/readiness requirements must remain enforced. Runtime containers must not receive migration credentials. Bootstrap the owner with the existing operator provisioning command, not an authentication bypass.

Use an explicit WEB_ORIGIN for the published Sites origin when preparing the deployment. This configuration alone does not implement the Sites authentication bridge.

## Local verification

Verified 2026-09-27 in the isolated worktree: 381 backend tests passed, zero failed and zero skipped (544.03 seconds). This includes authentication/session, RBAC, cross-tenant/direct-RLS, profitability, legacy acceptance and transaction-boundary regressions. A fresh PostgreSQL cluster migrated from base to 0013, downgraded to 0012, and upgraded again; actual revision is 0013 and the graph has one head. Ruff and pip dependency checks passed. JUnit evidence is retained locally at `.runtime/deployment-backend.xml`. Local test services and credentials remain in ignored runtime files; they are not deployment infrastructure. Hosted deployment, owner bootstrap and external proofs remain unverified until provisioning succeeds.
