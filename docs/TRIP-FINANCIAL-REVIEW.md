# Trip financial review — Batch 14

A single privileged owner/admin explicitly confirms financial closeout. Approval changes no revenue, expense, POD, trip lifecycle or original source record. No multi-stage or threshold approval engine is introduced.

`trip_financial_review_events` holds immutable status, reason, actor, server timestamp and monotonically increasing sequence. UNDER_REVIEW and APPROVED are explicit commands. NEEDS_ATTENTION change events are generated in the same transaction as financial mutations, including before the first approval, to protect an initial reviewer against stale values. READY_FOR_REVIEW is derived from the centralized policy when no current approval/review exists and no blockers remain. NEEDS_ATTENTION is derived whenever blockers exist. There is no client status PATCH.

Central policy is PostgreSQL `financial_review_blockers(trip_id)`, reused by API/UI calculation and the approval guard. Requirements: COMPLETED trip; at least one effective reviewed revenue; no active unreviewed revenue/direct expense; all non-voided advances fully settled; no unreconciled captured advances; no invalid expense allocation or changed imported advance source. Existing operational completion requirements remain unchanged. No optional receipt is silently reclassified as mandatory.

Review API: GET `/api/v1/trips/{id}/financial-review` (paged history), POST `/start`, POST `/approve`. Commands require explicit `records_confirmed=true`, latest event ID and UUID Idempotency-Key. The operator confirms all known records have synchronized and checks revenue, expenses, adjustments and advances. The server cannot observe unsent queues on disconnected devices; this attestation is explicit, not a guarantee of device synchronization. Future synchronized financial writes invalidate approval.

Approval uses the organization lock, refreshed permission and current event token, evaluates every policy blocker, appends history and audit, then commits with the command receipt. A changed token returns 409 even if the current records otherwise qualify. Duplicate identical retries return ALREADY_APPLIED. Driver, dispatcher, manager and accounting cannot approve. Restrictive owner overrides are respected.

Every insertion/update of revenue, expense root, closed-trip adjustment, advance or settlement appends a financial change event. Previous approvals remain in history. Changes after APPROVED/UNDER_REVIEW audit `financial_review.invalidated`. Approval is never silently restored when values return to their old amounts: another explicit approval is required. Reversals also invalidate. Underlying changes and event/audit writes share one transaction.

The existing financial card shows review status, specific blockers, history and review/approve controls. Server-calculated contribution remains visible while PROVISIONAL. The confirmation for settlement is separate from the financial-review confirmation. Driver App is unchanged.

The review response includes financial totals calculated under the same shared organization lock as its event token. The review section displays this snapshot so approval is tied to the displayed review totals, not an independently fetched older summary.
