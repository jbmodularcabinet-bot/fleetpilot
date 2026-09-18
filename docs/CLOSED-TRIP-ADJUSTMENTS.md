# Closed-trip administrative adjustments

Batch 9 extends the existing expense system. A trip must be COMPLETED. It remains closed: no lifecycle, Trip.version, completion timestamp, operational field, POD, evidence, assignment, source revision or original expense is edited.

## Model and effective values

`closed_trip_adjustments` is an append-only event table. Each entry records tenant, trip, expense, source revision, strictly increasing expense-local sequence, type, field, original effective value, new effective value, exact amount delta where relevant, reason, actor and database timestamp. Reversal is a new event referencing the original entry; APPLIED/REVERSED/REVERSAL are derived history states, not mutable flags.

`expense_effective_values` is a small database-maintained projection. Only the event trigger may write it. No public mutation endpoint exists. Existing lists, vehicle fuel history and trip totals use the projection if present, otherwise the original current revision. Detail returns original revisions separately from `effective`. Both tables have forced RLS and composite tenant/trip/expense references. Read authority for the projection follows the expense, so permitted drivers/operators see correct totals without gaining privileged history or correction access.

A positive corrected absolute amount is supplied as a decimal string; the server computes its signed delta. For example 300.00 -> 350.00 records +50.00. Money uses PHP, Decimal/NUMERIC and the Batch 8 0.01–10,000,000.00 range. JSON numbers, exponent notation, negative effective amounts, excessive precision and overflow are rejected. Fuel quantity/price and original multiplication remain unchanged; a privileged monetary adjustment is shown separately rather than pretending the original fuel calculation changed.

Administrative void excludes the expense from effective totals but preserves its original status, revisions and files. Reversing the void restores its prior contribution. Ordinary pre-closeout VOIDED expenses cannot be revived. Reviewed totals use the original review status and adjusted effective amount; an adjustment is applied by a trusted administrator, not a new driver submission.

## Scope and types

Supported: AMOUNT_CORRECTION, REFERENCE_CORRECTION, DESCRIPTION_CORRECTION, ODOMETER_CORRECTION (Fuel only), VOID_ADJUSTMENT and explicit REVERSAL. These cover all existing cost categories without moving the record between trips, tenants, vehicles or drivers.

Category changes are deliberately deferred: crossing Fuel/non-Fuel changes quantity/price requirements, while Other/Subcontractor carry additional requirements. Batch 9 does not introduce a broad replacement-expense schema. Unsupported CATEGORY_CORRECTION fails validation. There is no arbitrary JSON field mutation API.

Historical odometer corrections affect only the expense projection and fuel-history display. Vehicle.odometer and the monotonic reviewed_fuel_odometer remain unchanged, even when a corrected reading is lower. Reconciliation of an erroneously high trusted vehicle reading requires a separately authorized policy; no unrelated vehicle record is silently changed.

## Authorization and commands

Only OWNER and ADMIN receive `closed_trip_adjustments.read`, `.create` and `.reverse` by default. Existing restrictive overrides apply. Drivers, dispatchers, managers and accounting receive none. Creation/reversal refresh membership and permissions under the existing organization lock. History is owner/admin scoped at RLS as well as API level; projections follow ordinary expense visibility. Tenant UUID knowledge grants no access.

- GET `/api/v1/trips/{trip_id}/adjustments`: paginated history, 50 default, 100 maximum.
- POST `/api/v1/trips/{trip_id}/adjustments`: strict target_id, adjustment_type, new_value, expected_sequence and reason.
- POST `/api/v1/adjustments/{id}/reverse`: expected_sequence and reversal reason.

Every write requires a UUID Idempotency-Key. Existing durable command receipts are reused. Same actor/key/body replay returns the original result after current authorization; changed body conflicts. `expected_sequence` protects the expense projection; completed Trip.version is never incremented. Projection, event, immutable audit and replay receipt commit atomically.

Reasons require at least 10 non-whitespace characters, at most 2,000. No multi-stage approval engine: one trusted actor, explicit confirmation and permanent history.

## Reversal

Reverse the latest currently active adjustment for the expense first. This conservative last-in-first-out rule makes restoration deterministic across amount, text and void corrections. A reversal cannot itself be reversed; after undoing an incorrect adjustment, create a fresh adjustment if needed. Duplicate reversal, stale sequence and attempts to reverse an older dependent entry return conflict. No history disappears.

## UI and audit

A small Administrative adjustments section is added within completed Trip Detail's existing expense card. Forms, buttons, errors, spacing and confirmation use existing components/classes. Original submission and current effective value remain visible in expense history. No navigation or visual-token changes.

Confirmation: “This will not overwrite the original record. A permanent adjustment entry will be created.” Audit actions: closed_trip_adjustment.created, .applied, .reversed, with safe trip/target/field/old/new/delta/reason metadata. No receipt bytes, secrets or signed URLs are recorded.
