# FLEETPILOT BATCH 13 REPORT

Verification date: 17 September 2026.

BATCH 13 STATUS: CONDITIONAL PASS — local implementation verified; external launch gates remain UNVERIFIED.

DESIGN LOCK: PASS — existing shell/tokens/navigation preserved, originals 6/6 PASS, desktop/mobile browser assertions and screenshots inspected.

## Source audit

Read the Batch 8/9/11/12 reports and requested expense/fuel/correction/maintenance/recovery/security/design documents. Inspected actual Trip/completion rules, effective expense calculations, review/void state, immutable adjustment events/projections, maintenance separation, Decimal validation, customer/trip references, RBAC/RLS/audit, migration head and approved screens. Batch 12 evidence agrees with a 388-case baseline (310 backend, 43 frontend, 35 browser). No revenue/profitability service existed; Command Center financial figures were unavailable placeholders.

Policy decision: reviewed effective amounts are the contribution basis. Cash advances had only an operational-input classification, not a settled-cost policy, so contribution excludes them and displays them separately. Existing expense totals remain unchanged. Maintenance is never included. FINAL requires completed trip, reviewed revenue present and no unreviewed relevant inputs. No accounting/revenue-recognition assertion is made.

## Implemented

- Trip revenue: explicit PHP charges, strict owner/operator entry, review, ordinary open-trip void, history and safe original/effective display.
- Revenue corrections: extend existing Batch 9 append-only events with a revenue target and trigger-maintained projection. Amount/reference/description/void/reversal preserve original records. Owner/admin permission and meaningful reason required. No parallel correction system.
- Central server calculation: reviewed effective revenue minus reviewed effective direct costs; contribution and Decimal margin, submitted breakdowns, excluded cash advances and PROVISIONAL/FINAL. Zero revenue gives null margin; negative contribution is retained.
- Current closed-trip overlays recompute financial results immediately without changing Trip.version, completed state, milestones, POD or original financial submissions.
- Native Trip Detail financial section and lightweight filtered/paginated contribution list. Driver financial access remains denied; no nav/shell redesign. Command Center aggregation deferred and explicitly unavailable.
- Tenant-scoped APIs, forced RLS, immutable history/projection triggers, safe audit, durable replay, role/permission enforcement and aggregate queries without N+1.

See TRIP-REVENUE.md, TRIP-PROFITABILITY.md and PROFITABILITY-CALCULATION-RULES.md for exact semantics/endpoints.

## Migration

`0010_trip_profitability` follows `0009_maintenance`: adds trip_revenue and revenue_effective_values and extends shared closed_trip_adjustments with exclusive expense/revenue targets, composite references, sequence/reversal constraints and revenue policies/triggers. Existing expense adjustment rules are preserved. Indexes focus on tenant/trip/status/history rather than every column. Profitability itself has no stored snapshot table.

Forward/rollback/reapply PASS on isolated test DB. Development forward PASS; no development rollback/reset. Both catalogs report head 0010 and 28 enabled/forced RLS tables. Logs: `.runtime/batch13-migration-forward.log`, `batch13-migration-rollback.log`, `batch13-migration-reapply.log`, `batch13-development-migration.log`, `batch13-schema.json`. Rollback removes new revenue data/events and restores the prior expense-only schema; it is not a data-preserving production downgrade. Back up first.

## Executed gates

- Initial new backend suite: 23 passed.
- Full backend run: all 310 previous cases and 28 new cases passed; one new setup failed before financial assertions because of duplicate work-order helper arguments. Correcting that setup exposed its omitted required description. Both fixture issues were corrected without weakening assertions; final complete profitability suite: 29 passed, 0 failed, 39.54 seconds (`.runtime/batch13-target-final.log`). All 339 distinct backend cases are verified: 338 full-run passes plus the corrected case; overlapping reruns are not counted twice.
- Frontend: 47 passed, 0 failed; `.runtime/batch13-frontend-release.log`.
- TypeScript/lint/production Next.js build: PASS; `.runtime/batch13-typecheck.log`, `batch13-lint.log`, `batch13-build.log`.
- Python Ruff/compileall, pip check and npm dependency tree: PASS. No dependency additions or fresh vulnerability-feed audit.
- Original assets: 6/6 PASS.
- Production Chrome browser/E2E: 36 passed, 0 failed in 6.2 minutes (`.runtime/batch13-browser.log`), including all 35 prior cases. FastAPI started successfully; actual HTTP `/health` and `/ready` returned 200 in the maintenance regression. No physical-device claim.
- Total: 422 distinct passing cases (339 backend, 47 frontend, 36 browser), including the 388-case baseline and 34 new cases (29 backend, 4 frontend, 1 browser). The initial new backend fixture failure was fixed and its entire suite rerun; see the full-run/rerun accounting above. No unresolved failing case.
- Backend golden money/adjustment/reversal/maintenance exclusion/zero/negative/precision and tenant-role/API/direct PostgreSQL adversarial checks PASS.
- Browser golden: reviewed PHP25,000 revenue minus PHP10,300 costs = PHP14,700 contribution / 58.80%; closed-trip +PHP500 cost correction gives PHP14,200 / 56.80%; linked PHP12,000 maintenance remains excluded. Revenue adjustment to PHP26,000 preserves PHP25,000 original and yields PHP15,200 / 58.46%. Reload, history, list filtering, driver denial and responsive design PASS.
- Screenshot inspection: `.runtime/batch13-screenshots/batch13-financials-desktop.png` (1440px) and `batch13-financials-mobile.png` (390px). Native light cards/mint buttons/Inter and existing shell preserved; no horizontal page overflow. Full-page history is intentionally long.
- Local performance: 302 successful requests, concurrency 1, real PostgreSQL with in-process ASGI and 20 synthetic trips. Single summary p50/p95 10.04/13.30ms; list 13.55/16.40ms; date-filtered list 13.84/17.75ms. Zero errors. List SQL count is 10 for both 1 and 20 rows, including authentication/tenant context. This is a bounded local query check, not network/production capacity. Evidence: `.runtime/batch13-performance.json`.

Development migration initially caught an SQL CASE-parenthesis syntax error; the transactional migration was corrected before successful forward/rollback/reapply. Original UTF-8 screen text was preserved while editing. A formatter also normalized nine existing Python files without intended behavioral changes; inventory identifies them. No previous test was deleted or skipped.

## Security and limitations

Internal security review: BATCH-13-SECURITY-REVIEW.md. Exact Decimal/PHP, trusted corrections, original immutability, tenant/role denial, audit and maintenance exclusion are release-critical; no unavailable environment is used to excuse a failure.

PHP only. Contribution is not net profit, cash collection, fully loaded profitability, an invoice, a ledger, VAT or revenue recognition. No overhead/depreciation/maintenance allocation. Revenue entry is online-only. Cash advance settlement and administrative review of old unreviewed completed-trip expenses remain outside scope. Per-record revenue history is unpaginated; master filter dropdowns use the first 100 permitted records, while API filters accept authorized UUIDs. Cancelled trips are read-only.

## UNVERIFIED launch blockers

Physical Android, actual Safari/iOS, Docker execution, remote CI, public HTTPS staging, production object storage/IAM, external monitoring, remote backup/restore, deployed tenant/cross-driver isolation, staging load and independent security assessment remain UNVERIFIED. Prior local recovery/load evidence is not production certification and does not certify remote revenue recovery.

Recommended Batch 14: complete external launch-verification gates and explicitly decide financial review/advance-settlement policy before expanding scope. No AI, GPS, invoices, ledger, customer portal or fully loaded profitability is started. Stop after Batch 13.

## Files and final scope

17 files created and 21 modified, itemized in BATCH-13-FILES.md. No new dependencies, sidebar items, accounting model or Driver financial functionality. A final copy-only correction distinguishes ordinary permanent voids from append-only administrative entries; frontend/static/build checks were rerun after it. Browser golden screenshots precede that wording-only change. The final build first rejected an omitted API_INTERNAL_URL as designed; rerunning with explicit local http://127.0.0.1:8100 succeeded. No configuration guard was relaxed.

Local internal review found no unresolved financial-integrity, authorization, RLS or design release blocker in the tested scope. Risks remain: external deployment unverified; single-actor administrative corrections; organization-level write serialization can limit high concurrency; high-volume and long-history performance is unverified. No claims of independent security certification. Batch 13 complete; Batch 14 not started.
