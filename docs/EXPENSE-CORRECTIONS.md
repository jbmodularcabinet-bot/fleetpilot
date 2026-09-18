# Expense correction, review and void history

Batch 9 adds a separate privileged append-only overlay for COMPLETED trips. The ordinary Batch 8 revision/void APIs remain closed-trip read-only. See [CLOSED-TRIP-ADJUSTMENTS.md](CLOSED-TRIP-ADJUSTMENTS.md).

There is no generic expense PATCH or DELETE. Original financial details are immutable. Correction appends a full `expense_revisions` row with incremented revision number, reason, actor and server timestamp, then atomically advances the root's deferred composite foreign key. Old amount/category/notes/vendor/date/fuel data remain queryable. Currency is always PHP and relationship identity never changes.

Correction returns the expense to SUBMITTED and clears the current review display. Review records actor, server timestamp and optional note without modifying financial detail or receipt bytes. A later correction/void audit includes the previous revision/status/review actor/time/notes so prior review history is retained. Voiding requires a reason and stores actor/time; it is terminal, preserves revisions/evidence and removes the current amount from both totals. Reviewer actions use expected trip version and stable command keys; conflicting concurrent changes receive 409.

Receipt replacement is explicit through `supersedes_id` on upload. Only an ACTIVE receipt from the same SUBMITTED expense can be superseded. Original metadata and object bytes remain; new metadata has its own UUID/key/checksum. Ordinary hard deletion and silent overwrite are absent. Reviewed receipts require a privileged financial correction before further uploads; voided and closed-trip evidence is read-only.

Corrections and review are permitted only before trip closeout. Completed/cancelled trips require a future administrative workflow; Batch 8 adds none. Review is operational verification, not accounting approval, reimbursement or legal certification.
