# Trip contribution — Batch 13

> Current policy: Batch 14 supersedes the automatic FINAL/advance handling described below. See [PROFITABILITY-FINALIZATION-POLICY.md](PROFITABILITY-FINALIZATION-POLICY.md), [CASH-ADVANCE-SETTLEMENT.md](CASH-ADVANCE-SETTLEMENT.md) and [TRIP-FINANCIAL-REVIEW.md](TRIP-FINANCIAL-REVIEW.md). The remaining arithmetic and historical Batch 13 details are retained.


Trip Detail gains a native Financial performance card with reviewed Revenue, Direct trip cost, Contribution, Contribution margin, PROVISIONAL/FINAL, submitted totals, unreviewed count and category breakdowns. Original revenue and shared correction history remain visible. Negative values use exact string formatting. Zero-revenue margin is N/A.

A lightweight `/trips/profitability` page is linked from Dispatch and Trip Detail without changing sidebar or Driver navigation. It supports trip/customer search, customer/vehicle/driver filters, scheduled-pickup date range, trip lifecycle status, ascending/descending pickup sorting and pagination. API additionally supports trip-number sorting. Financial status is displayed; the status filter refers to lifecycle status. Dropdown choices use the existing first 100 permitted master records; API UUID filters support any authorized record.

- GET `/api/v1/trips/{trip_id}/financials`
- GET `/api/v1/trips/{trip_id}/profitability` (same calculation)
- GET `/api/v1/profitability/trips`

Responses include currency, basis REVIEWED_EFFECTIVE, reviewed/submitted revenue and direct-cost totals, category breakdowns, excluded cash advances, contribution, margin, status, unreviewed count and calculated_at. Pagination is 20 default/100 maximum. Sorting uses explicit allowlists, IDs use UUID validation and date bounds require timezones. Frontend Philippine calendar dates are sent with explicit +08:00 boundaries.

Each financial endpoint requires trip_financials.read, trip_profitability.read and expenses.read so a denied cost permission cannot produce a misleading zero-cost calculation. Revenue detail/list uses trip_financials.read. Owner/admin/manager/accounting are default financial roles; dispatcher/driver/maintenance are denied. Only owner/admin may use administrative adjustments. Tenant UUID knowledge never grants access.

Command Center aggregation remains unavailable and is labelled as such. No decorative chart, new dashboard, customer/vehicle aggregation engine, driver ranking, accounting, invoice, GPS, AI or offline financial-entry workflow is added. Approved shells, typography, colors, icons and assets remain locked.

Read PROFITABILITY-CALCULATION-RULES.md for inclusion/finalization semantics and TRIP-REVENUE.md for record/correction behavior. External launch blockers remain UNVERIFIED as recorded in BATCH-13-REPORT.md.
