# Expense offline synchronization

Batch 8 extends Batch 7's SAME IndexedDB actions store, queue, Web Lock, foreground/manual/background triggers and server receipt table. No alternate sync worker, authentication or money authority exists.

An expense command contains a stable UUID, expected trip version, client capture time and strict category/decimal-string payload. Selected receipt File/Blob records are queued atomically with the parent, with increasing versions and a dependency on its accepted expense ID. Reconnect rechecks current session, tenant, active linked driver, assignment and permissions. Parent success resolves the receipt's destination; receipt replay uses its original key and unchanged body/version. Receipt commands reuse the authorized `/expenses/{id}/evidence` endpoint rather than a second upload system.

Saved locally acknowledges the IndexedDB commit only. Server totals exclude pending costs until accepted. Trip current_status/milestone are not changed by expense projection. Local pending expenses increment the projected version so later legitimate queued operations retain ordering. Pending evidence survives page restart through existing Blob persistence. Accepted files release queue Blob copies. Same-key lost-response recovery replays the durable receipt rather than adding cost twice.

Limits and failures remain Batch 7's: 100 pending commands, 40 MiB queued evidence, up to 10 selected images, 12-hour offline lease, bounded transient backoff, explicit conflict attention and no automatic rebasing. Closed/reassigned trips, changed permissions, invalid money or low odometers fail server revalidation. Operators resolve the conflict; the queue cannot override history. Expense detail/receipt browsing requires connectivity unless the relevant authorized list was already cached. Private server receipt downloads are not cached by the worker.

Browser eviction/device loss can destroy unsynchronized work; storage is not encrypted at rest. OS background execution, physical installation, Safari behavior and production deployment are not established by local Chromium tests. Do not imply guaranteed background delivery.
