# MVP1 deterministic intelligence rules

Version: mvp1-contribution-v1. Product policy defaults are configurable per organization, not industry benchmarks. Owner/admin settings changes require organization.manage and append an audit entry.

| Rule | Exact trigger and qualification |
|---|---|
| Missing reviewed revenue | Reviewed cost records exist without reviewed revenue records; prioritize the incomplete input, not a claim of commercial failure |
| Negative contribution | Reviewed contribution < 0; explain revenue and direct cost, retain provisional/data-quality qualifications |
| Low contribution margin | Non-negative contribution and unrounded margin below configured 15% default; not a net-loss claim |
| Direct-cost pressure | Direct cost exceeds configured 70% share of reviewed positive revenue |
| Financial review incomplete | Actual financial-governance status/blockers, missing reviewed inputs or noncurrent explicit approval |
| Advance attention | Unreconciled capture, positive outstanding confirmed issuance, or actual settlement/source conflict |
| Material financial change | Supported amount-correction/reversal event with absolute amount delta >= PHP 1,000 default; show historical source before/after and event ID, not invented historical portfolio balances |
| Cost concentration | Category share >= configured 50% default; describe concentration, not waste, theft, consumption or driver performance |

Threshold checks use exact Decimal arithmetic before display rounding. Material comparison is unavailable when supported history is absent or not authorized; manager/accounting users receive an explicit history-availability warning rather than hidden completeness certification.

Each finding includes its stable rule/entity/event key, version, priority, supporting values, comparison basis, data-quality qualification, recommended review action, authorized link and calculation timestamp. Results are deduplicated and deterministically ordered. The owner brief is generated from validated report data without an external AI model.

Source navigation returns owners to existing trip financial workflows. A selected-trip report includes the existing FinancialPanel so permitted accounting users can inspect revenue and settlement even when they lack general operational trip access. No reporting GET performs source-record mutations.

Fuel cost share alone never supports km/L, cost/km, theft, poor driving or driver ranking. No savings forecast or arbitrary customer recommendation is generated.
