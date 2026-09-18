# Maintenance costs — Batch 11

Maintenance cost items are a separate domain from trip_expenses. An optional trip_id on a work order supplies context only. No receipt, service completion or cost item creates or changes a trip expense. The release test keeps a PHP 5,000 trip total unchanged beside PHP 12,000 maintenance.

Each append-only line has PART, LABOR or OTHER type, description, quantity, unit_cost, calculated total_cost, optional vendor/reference, actor and timestamp. API monetary/quantity input is a decimal string; floats, exponent notation, negatives, excess precision and overflow are rejected. PostgreSQL NUMERIC and Python Decimal are used. Quantity is positive, at most 100,000 with three decimal places; unit cost at most 10,000,000 with four decimal places. Each line total is bounded to 10,000,000 and rounded ROUND_HALF_UP to centavos. PostgreSQL checks the multiplication/rounding too. Server sums line totals; clients cannot submit a trusted total.

Example PART 1,234.56 + LABOR 500.00 + OTHER 100.10 = PHP 1,834.66 exactly. PHP only. Costs cannot be edited/deleted, and no costs may be appended after COMPLETED/CANCELLED. A correction workflow for closed maintenance is deferred rather than silently rewriting a line.

Private maintenance receipt, service invoice, before and after photo types reuse the established image evidence service. Images only; no PDF, OCR, purchasing, depreciation, ledger or financial dashboard. Owner cost/evidence mutations require separate explicit permissions and durable idempotency keys.
