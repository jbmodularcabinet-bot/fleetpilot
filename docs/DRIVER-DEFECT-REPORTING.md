# Driver defect reporting — Batch 11

A driver report stores organization, vehicle, server-derived linked driver/user, optional trip, severity, category, immutable original description, client reported time, server received/created times and review status. Client time is informational; shared sync receipts flag a clock difference exceeding 24 hours. Server time governs workflow.

Severity: MINOR, MODERATE, SERIOUS, CRITICAL. Categories: ENGINE, BRAKES, TIRES, ELECTRICAL, LIGHTS, SUSPENSION, STEERING, COOLING, TRANSMISSION, BODY, SAFETY_EQUIPMENT, OTHER. Every report requires a nonblank description of at least three characters, including OTHER. Severity is selected by the driver, not inferred.

## Ownership and review

An active linked driver may report only a current fleet-assigned vehicle or a vehicle on their own nonterminal trip (including SCHEDULED). If trip_id is supplied, that exact own nonterminal trip must match the vehicle; a separate fleet assignment does not excuse a manipulated trip ID. Driver identity is never accepted from the payload.

Drivers read only their own reports and evidence. Submission and new evidence recheck current vehicle ownership. Owners/authorized maintenance staff can review or dismiss with a reason. REPORTED → REVIEWED or DISMISSED; REVIEWED → WORK_ORDER_CREATED or DISMISSED; WORK_ORDER_CREATED → RESOLVED only through completed linked work. Original fields cannot change; PostgreSQL guards the status graph and immutable fields. Work-order relation is stored on the work order rather than duplicated on the report.

## Offline behavior

The existing Driver home and active trip provide Report vehicle issue. Assigned vehicle choices are cached through the established authenticated cache. A report and up to ten selected photos are committed to the existing IndexedDB queue before Saved locally is shown. The existing 100-action/40 MiB queue limits and account/session boundary apply. Browser eviction is still possible; local save is not server acknowledgment.

The defect command is independent of trip.version because a fleet assignment may exist without a trip. It uses the same actor-bound durable server receipt, request digest, queue lock, retries, identity validation and outcome vocabulary as earlier batches. Dependent photo commands wait for the server defect ID. A lost response retries the same key; committed results return ALREADY_APPLIED. Queue entries and blobs are removed/released only after acknowledgment. Defects do not advance operational trip milestones or versions. Photos sync separately, so a report may precede its photo. Review that closes the attachment window before a delayed photo sync produces Needs attention; it does not silently overwrite history.

Page close/reopen and synthetic offline/lost-response behavior are tested in desktop Chrome. Physical force-kill, storage persistence on actual Android, Safari/iOS and remote deployment remain UNVERIFIED. No new offline engine or public upload path was added.

## Evidence

Reuse existing storage provider, checksum, image normalization and rollback cleanup. JPEG/PNG/WebP only; MIME, extension and decoded image must agree. Maximum 5 MiB per file and 16 million pixels; maximum twelve retained objects per parent. The UI queues at most ten photos at once. Receipt/invoice types are images, not PDFs. Normalized PNG data strips original metadata. Keys are random private objects and never returned as public paths.

GET /api/v1/maintenance-evidence/{id} requires authenticated tenant/parent permission and driver ownership, verifies checksum and emits private no-store handling. Neither UUID possession nor filename authorizes access. Ordinary users cannot delete or replace submitted images.

Endpoints: GET /driver/maintenance-vehicles, POST/GET /driver/defects, GET /defects/{id}, POST /defects/{id}/evidence, POST /defects/{id}/review or /dismiss. Creating a work order with defect_report_id performs the explicit create-work-order operation using the shared work-order endpoint.
