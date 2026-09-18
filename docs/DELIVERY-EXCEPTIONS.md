# Delivery exceptions — Batch 5

## Explicit categories

RECIPIENT_UNAVAILABLE, WRONG_ADDRESS, INCOMPLETE_ADDRESS, DELIVERY_REJECTED, DAMAGED_CARGO, PARTIAL_DELIVERY, SITE_ACCESS_ISSUE, VEHICLE_ISSUE, DRIVER_ISSUE and OTHER. OTHER requires at least three non-whitespace characters of notes. Exception photos are optional. Partial delivery fails this attempt; quantity reconciliation is outside this batch.

## Failure and history

At ARRIVED_DELIVERY, UNLOADING_STARTED or UNLOADING_COMPLETED, the assigned driver or permitted operator can report an issue. One atomic command marks the attempt FAILED, creates an OPEN DeliveryException and records DELIVERY_ATTEMPT_FAILED plus audits. It never creates POD or marks the trip DELIVERED.

Failed attempts preserve their number, arrival/completion times, actor, notes and evidence. A failed attempt cannot be rewritten as successful. The owner sees all attempts in numbered chronological history (newest first, paginated), with the exception and evidence attached to the original attempt.

## Resolution and retry

An authorized owner/operator may authorize an on-site retry with resolution notes. The exception becomes RETRY_AUTHORIZED and records resolver/time, audit and DELIVERY_RETRY_AUTHORIZED milestone. Drivers cannot authorize their own retry. Unresolved exceptions block ordinary progress and new attempts; existing authorized cancellation remains available and preserves history.

A retry creates the next numbered attempt and DELIVERY_RETRY_STARTED event. No trip milestone is silently reset. Previously completed unloading remains recorded; successful POD still requires UNLOADING_COMPLETED. The successful second attempt produces its own POD and evidence while the failed first attempt stays FAILED.

Example: Attempt 1 fails with RECIPIENT_UNAVAILABLE and “Recipient contact unreachable.” The operator records that the recipient is now present and authorizes retry at the same stop. Attempt 2 records Pedro Reyes, required photo and driver confirmation. Attempt 2 and the trip become DELIVERED; Attempt 1 and its exception/photo remain visible.

## Limits and protection

Retry means continuation at the same recorded delivery stop. Re-routing, changed addresses, return legs, repeated travel, administrative corrections and reconciliation are deferred. Resolution is explicit authorization to retry, not a claim of successful delivery.

Tenant/RBAC and assigned-driver checks cover creation, reading, files and resolution. Database guards protect historical attempts and immutable evidence. Version checks and organization locks reject competing or repeated submissions safely. See [PROOF-OF-DELIVERY.md](PROOF-OF-DELIVERY.md) and [DELIVERY-EVIDENCE.md](DELIVERY-EVIDENCE.md).
