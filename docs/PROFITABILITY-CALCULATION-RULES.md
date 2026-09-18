# Profitability calculation rules — Locked V1

> Current policy: Batch 14 supersedes the automatic FINAL/advance handling described below. See [PROFITABILITY-FINALIZATION-POLICY.md](PROFITABILITY-FINALIZATION-POLICY.md), [CASH-ADVANCE-SETTLEMENT.md](CASH-ADVANCE-SETTLEMENT.md) and [TRIP-FINANCIAL-REVIEW.md](TRIP-FINANCIAL-REVIEW.md). The remaining arithmetic and historical Batch 13 details are retained.


The authoritative service is `apps/api/fleetpilot/profitability.py`. Profitability is computed from current effective records, not persisted as a potentially stale snapshot. The frontend formats server values only.

## Basis

**Revenue:** effective non-voided REVIEWED trip revenue.

**Direct cost:** effective non-voided REVIEWED trip expenses: FUEL, TOLL, PARKING, DRIVER_ALLOWANCE, HELPER_ALLOWANCE, LOADING_FEE, UNLOADING_FEE, SUBCONTRACTOR and OTHER. Existing expense revisions and Batch 9 overlays are the only source of cost; no duplicate expenses are created.

DRIVER_CASH_ADVANCE is excluded and shown separately. Batch 8 classified advances only as operational inputs, not settled costs. Counting both advances and later receipts risks double-counting. No settlement engine is added. The existing expense panel retains its broader operational total; the financial panel explicitly names reviewed direct cost and its exclusions.

Maintenance is always excluded. The service never reads maintenance cost tables, even when a work order has trip_id context. No depreciation, overhead, insurance, loans, salaries, VAT, taxes or maintenance allocation is introduced.

Submitted totals include SUBMITTED plus REVIEWED non-voided eligible records. They are shown beside reviewed totals and unreviewed-count warnings. Voided originals and administrative void overlays are excluded from both totals. Reversal restores prior effective values automatically.

## Status

FINAL requires a COMPLETED trip, at least one non-voided REVIEWED revenue record, and zero SUBMITTED eligible revenue/expense records. Otherwise PROVISIONAL. Cash advances are excluded from both direct cost and the review-completeness check. FINAL means operational inputs are reviewed, not paid, recognized, audited or fully allocated accounting profit.

A completed trip with unreconciled SUBMITTED expenses remains PROVISIONAL. Batch 13 does not reopen trips or relax the existing prohibition on ordinary post-closeout expense review. Future administrative review policy would require explicit scope. New unreviewed revenue makes a previously FINAL calculation PROVISIONAL; trusted effective adjustments to reviewed inputs preserve review status and immediately recompute the result.

## Arithmetic

Contribution = reviewed effective revenue − reviewed effective direct cost.

Contribution margin = contribution / reviewed effective revenue × 100.

Money remains exact Decimal/NUMERIC with two decimal places. Margin uses Decimal ROUND_HALF_UP to two places. Revenue zero returns margin null (N/A) and contribution = negative cost. Negative contribution is preserved, never clamped. No binary floating-point monetary arithmetic or frontend formula is used.

Golden: 25,000 revenue − 10,300 cost = 14,700 contribution, 58.80%. A +500 cost adjustment yields 10,800 cost, 14,200 contribution, 56.80%. A subsequent +1,000 revenue adjustment yields 26,000 revenue and 15,200 contribution. Original amounts remain unchanged. Separately, 25,000 revenue − 10,000 direct cost alongside 12,000 linked maintenance still yields 15,000 contribution. Zero revenue and 1,000 cost yield −1,000/N/A. Revenue 10,000 and cost 12,500 yield −2,500/−25.00%.

## Consistency and performance

Financial reads take a shared organization lock; financial writers use the existing exclusive lock. Revenue and expense aggregation therefore describe one coherent financial state. Trip lists use one page query, one count and two grouped aggregate queries for all page IDs, not one set per trip. Tenant/parent/status indexes support the lookups. No speculative snapshot cache or architecture redesign.

This is contribution analysis, never Net Profit or fully loaded profitability. Local timing evidence is not production-scale BI certification.
