# Trip revenue — Batch 13

Revenue is an operational charge attributable to a trip, not cash collected, an invoice, tax treatment or accounting recognition. PHP only. Owner/admin/manager/accounting receive explicit financial read/create/review/void permissions by default; dispatcher, driver and maintenance roles receive none. Restrictive permission overrides remain authoritative on the server.

## Records and commands

`trip_revenue` stores the original trip/tenant/type/amount/currency/description/reference, submitter and timestamp. Types: BASE_TRIP_CHARGE, SURCHARGE, WAITING_TIME, SPECIAL_HANDLING, OTHER. OTHER needs three trimmed explanation characters. Status is SUBMITTED, REVIEWED or VOIDED; review and void record actors/timestamps. Original money and ownership fields never change. Cancelled trips reject writes. New charges may be appended to completed trips without reopening them; they remain SUBMITTED until explicit review, making contribution provisional in the meantime.

Amount is a plain positive decimal string, PHP 0.01–10,000,000.00, at most two decimals. JSON numbers, exponent notation, negative values, NaN/infinity, excess precision and overflow are rejected. PostgreSQL NUMERIC and Python Decimal are authoritative. No client total/status/actor/organization is accepted.

- GET/POST `/api/v1/trips/{trip_id}/revenue` (bounded list pagination).
- GET `/api/v1/trip-revenue/{id}` (original, effective values and authorized history).
- POST `/api/v1/trip-revenue/{id}/review`: expected_sequence.
- POST `/api/v1/trip-revenue/{id}/void`: expected_sequence and meaningful reason; open trips only.
- POST `/api/v1/trip-revenue/{id}/correct`: target_id, expected_sequence, adjustment_type, new_value and reason.
- POST `/api/v1/adjustments/{id}/reverse`: shared Batch 9 reversal endpoint.

All writes require UUID Idempotency-Key, use the existing organization lock and durable command receipts, and commit the record/projection/audit/receipt together. Matching replay returns the original result; altered data or stale sequence conflicts. Current authorization is checked before replay. No trip version, milestone, completed timestamp or operational field is changed.

## Shared correction architecture

Batch 9 `closed_trip_adjustments` now supports exactly one expense or revenue target, with composite tenant/parent references. Expense events retain their original rules. Revenue corrections use the same append-only events, reasons (10 non-whitespace characters), effective projection trigger, privileged OWNER/ADMIN read/create/reverse capabilities, idempotency and latest-active-first reversal policy. They may correct submitted/reviewed revenue on an open or completed trip. No second correction-history table/framework was created.

Revenue supports amount, reference, description, administrative void and reversal. Odometer/category/currency/ownership mutation is forbidden. `revenue_effective_values` is trigger-maintained; it cannot be directly edited by an ordinary command. A monetary correction supplies the new absolute positive amount and records the signed delta. For example 25,000 → 26,000 preserves the original charge and records +1,000. A separate SURCHARGE record is also supported and requires review before entering contribution.

Reviewed corrections by a trusted administrator retain review status; corrections to SUBMITTED revenue do not silently review it. Completed-trip voiding uses an explicit administrative void adjustment. Open-trip ordinary void is explicit, audited and terminal. Reversing an administrative void restores the previous contribution; an ordinary void cannot be revived. Historical originals/events are never deleted by application APIs.

## Security and audit

Revenue and its projection force RLS; drivers cannot directly enumerate either table. Database triggers independently enforce trusted roles, restrictive permissions, original immutability, review/void transitions, event sequence and reversal dependencies. Audit events include trip_revenue.created/reviewed/voided/corrected plus shared closed_trip_adjustment.created/applied/reversed. Calculation reads do not generate audit noise. No secrets or receipt bytes enter financial audit metadata.

The native Trip Detail financial card supports entry, review, correction/void confirmation, original/effective values and correction history. No Driver revenue controls or offline revenue queue were added. History in the per-record detail response is currently unpaginated; revenue lists themselves are paginated.
