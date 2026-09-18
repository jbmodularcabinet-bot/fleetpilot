# FleetPilot Batch 15 — Master Production Baseline

Status at entry: Batch 14 CONDITIONAL PASS; 455 distinct automated tests previously verified.

## Objective
Close the gap between a locally verified SaaS and a production-verifiable release without redesigning working FleetPilot architecture or weakening existing security, financial, tenancy, or UI contracts.

## Locked baseline
- Next.js 16 / React / strict TypeScript web application.
- FastAPI + SQLAlchemy backend.
- PostgreSQL authoritative persistence with forced RLS and tenant context.
- Same-origin opaque session authentication.
- Append-only audit and immutable financial governance history.
- Existing approved FleetPilot visual system and Driver App remain locked.
- Batch 14 cash-advance settlement and explicit financial-review rules remain authoritative.

## Batch 15 mandatory gates
1. Establish Git provenance: first clean baseline commit, protected default branch, remote, release tag.
2. Execute CI remotely from the committed baseline; no local-only substitution.
3. Execute production Docker images and compose path; record image digests and health evidence.
4. Deploy controlled HTTPS staging with synthetic data only.
5. Verify remote private object storage, IAM, upload/read/delete, and backup/restore.
6. Configure external monitoring with safe allowlisted telemetry and alert verification.
7. Verify deployed tenant, role, and cross-driver isolation against staging.
8. Execute physical Android and actual Safari/iOS acceptance where available.
9. Execute staging recovery and controlled load checks.
10. Run full regression and issue PASS / CONDITIONAL PASS / FAIL with evidence.

Do not begin new product features, AI, GPS, invoicing, payroll, ledger, customer portal, or redesign work inside Batch 15.