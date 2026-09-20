# MVP1 reporting calculation rules — v1

## Authority and terminology

Use the existing profitability.py calculation and database financial-governance functions. Reporting does not recalculate finalization from a simplified record-count rule. Approved source corrections, voids, reversals and legacy acceptance are inherited from the established effective-value service.

Contribution = reviewed effective operational revenue minus reviewed effective direct trip cost.
Contribution margin = contribution / reviewed revenue * 100; revenue zero returns null / N/A.
Portfolio contribution = sum of included trip contributions.
Portfolio weighted margin = total contribution / total reviewed revenue * 100. Never average trip margins.

Money is Decimal/NUMERIC, formatted with explicit ROUND_HALF_UP to cents. API values are decimal strings. Negative contribution and margins remain negative. The browser formats strings; Number is used only to bound a decorative percentage-bar width, never to generate financial totals.

Required qualification: Contribution equals reviewed operational revenue minus reviewed direct trip costs. It excludes maintenance allocation, depreciation, financing, insurance, company overhead, and taxes. It is not net profit or cash collected.

## Confidence

A trip with no reviewed direct expense records is not certified cost-free. Missing reviewed revenue or direct costs creates a visible warning. Positive, negative and zero classifications require both reviewed revenue and cost inputs; insufficient-data trips are counted separately. Existing FINAL/PROVISIONAL status remains authoritative, with explicit financial approval and cash-reconciliation blockers preserved.

Submitted totals include reviewed and submitted eligible records as defined by the existing service. They are not substituted for reviewed figures. Maintenance and capital/company costs remain outside direct contribution.

## Advances

Captured DRIVER_CASH_ADVANCE records remain excluded from direct cost. They do not establish confirmed issuance or an outstanding balance.

Confirmed issuance is immutable funding; active reviewed expense applications and cash returns reduce its balance. Reversals restore the applicable prior settlement state. Voided issuance is shown separately and excluded from active issuance totals. Captured records and issuance linked to those captures are not added together as an expense. A captured-only PHP 5,000 example remains an unreconciled capture, not PHP 5,000 confirmed outstanding.

## Retained synthetic validation, freshly checked in the demo

| Example | Revenue PHP | Direct cost PHP | Contribution PHP | Margin |
|---|---:|---:|---:|---:|
| A | 22,000.00 | 9,850.00 | 12,150.00 | 55.23% |
| B | 18,000.00 | 12,000.00 | 6,000.00 | 33.33% |
| C | 14,000.00 | 15,200.00 | -1,200.00 | -8.57% |
| D | 20,000.00 | 3,200.00 | 16,800.00 | 84.00% |
| Total | 74,000.00 | 40,250.00 | 33,750.00 | 45.61% weighted |

Fuel 24,150.00; toll 5,400.00; driver allowance 5,300.00; helper allowance 3,000.00; loading 1,200.00; unloading 700.00; parking 500.00. Total 40,250.00. Fuel share is 60.00%.

Four trips remain PROVISIONAL and zero FINAL. Three have positive reported contribution and one negative. The 84% example validates advance exclusion, not exceptional real-world fleet efficiency.

Evidence: .runtime/batch16/demo-public/golden-overview.json and result.json. These are synthetic demonstration results, not a financial statement for a customer.

## Technical references

Python Decimal: https://docs.python.org/3/library/decimal.html
PostgreSQL locks: https://www.postgresql.org/docs/current/explicit-locking.html
The implementation uses the installed project versions and existing organization-locking contract; documentation references do not replace executed verification.
