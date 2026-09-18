# Delivery evidence and exceptions — Batch 5

## Policy and workflow

`fleetpilot/delivery_policy.py` is the authoritative baseline policy; the attempt-list response supplies the same limits to the UI. A successful POD requires a nonblank recipient name, explicit confirmation from the assigned driver (or an authorized operator recording that driver's confirmation), a server delivery timestamp, and at least **one active delivery photo**. Signature is **optional**. A supplied signature requires explicit recipient-signature confirmation. Role and notes are optional. No recipient-unavailable success alternative exists; use a failed attempt.

The authenticated submitting user and assigned domain driver are recorded separately. Operator submission is clearly labelled as recording the assigned driver's confirmation; it does not impersonate the driver account. A signature is operational evidence, not a legal non-repudiation assertion.

Hierarchy: Organization → Trip → DeliveryAttempt → Evidence/POD/Exception. Each attempt gets a unique increasing number within its trip. An attempt opens only at ARRIVED_DELIVERY, UNLOADING_STARTED or UNLOADING_COMPLETED; its `arrived_at` records contemporaneous arrival confirmation when the attempt is opened, not measured GPS or a backdated arrival. First physical arrival remains in the Batch 4 milestone history. Only one attempt may be open at a time.

Successful submission at UNLOADING_COMPLETED freezes the attempt as DELIVERED, inserts POD, records DELIVERED milestone/audits and moves the trip to DELIVERED in one database transaction. The ordinary `deliver` transition returns 409. No other Batch 4 state progression is loosened. Delivery attempt creation/uploads may already exist as private in-progress records before final submission; a failed submission does not falsely deliver the trip.

Owners/admins/managers/dispatchers can review submitted POD once. Review records reviewer/time/audit and leaves recipient, notes and evidence unchanged. New trips require reviewed POD before the existing operational closeout action can mark COMPLETED. Neither state creates accounting events or means an invoice is paid.

## Failure and retry

Exceptions: RECIPIENT_UNAVAILABLE, WRONG_ADDRESS, INCOMPLETE_ADDRESS, DELIVERY_REJECTED, DAMAGED_CARGO, PARTIAL_DELIVERY, SITE_ACCESS_ISSUE, VEHICLE_ISSUE, DRIVER_ISSUE, OTHER. OTHER requires at least three non-whitespace characters of notes. All exception types fail the entire attempt; PARTIAL_DELIVERY does not introduce quantity reconciliation or partial financial fulfillment. Exception photos are optional.

Failure atomically freezes the attempt as FAILED, creates an OPEN exception and records DELIVERY_ATTEMPT_FAILED plus audits. It never creates a successful POD or changes the trip to DELIVERED. Subsequent ordinary progress and new attempts are blocked while an exception is OPEN. Cancellation remains the existing authorized terminal exception action; cancellation retains any evidence/attempt/exception history.

An authorized operator may explicitly authorize an **on-site retry at the same recorded stop**, with mandatory resolution notes. This changes only exception resolution fields to RETRY_AUTHORIZED and records DELIVERY_RETRY_AUTHORIZED. It does not convert Attempt 1 to a success, reset trip milestones, change address or claim new travel. A new attempt receives the next number and records DELIVERY_RETRY_STARTED. Previously completed loading/unloading capture remains valid; POD still requires the trip to be at UNLOADING_COMPLETED. A retry after failure during/after unloading therefore resumes from the existing milestone. Driver cannot authorize its own retry.

Different-address re-routing, return-to-depot, re-dispatch, cargo reconciliation, repeated travel legs and administrative corrections are deferred. Operators should cancel and plan separate work when the existing trip cannot truthfully continue at its recorded stop. No automatic retries or offline submissions exist.

## Evidence limits and storage

- JPEG (`.jpg`/`.jpeg`), PNG (`.png`), WebP (`.webp`), matching MIME header and decoded format.
- Nonempty; at most **5 MiB incoming and stored**, **16 million pixels**, one frame. Animated, malformed, executable, SVG and unsupported uploads are rejected. Up to **12 retained files per attempt**, including superseded versions.
- Files use a bounded raw image request body rather than unbounded multipart parsing. Image decoding verifies the actual format. Pixel-only PNG re-encoding removes EXIF/GPS, comments and appended payloads. The stored checksum covers normalized bytes, not the original upload. Original filename is metadata only and cannot supply a path.
- No client capture timestamp is asserted; `captured_at` remains null. Server upload time, uploader, content type, normalized size, SHA-256 checksum and evidence type are recorded.
- The storage protocol exposes immutable `put`, `read`, and rollback-only `discard_uncommitted`. Domain logic does not manipulate filesystem paths. Local keys use tenant UUID plus random evidence UUID and are never returned to clients.
- Local development/test roots default to ignored `.runtime/evidence-development` and `.runtime/evidence-test`. `EVIDENCE_STORAGE_ROOT` optionally selects an operator-controlled private directory outside web assets. The API never mounts it as static content. No `/uploads` public route exists.
- **Production object storage: NOT CONFIGURED / UNVERIFIED.** Production evidence storage operations fail with 503. An S3-compatible adapter can implement the same interface after credentials, private-bucket policies, atomic writes, backup and deployment checks are supplied. No cloud credentials or signed URLs are invented.

Validation uses Pillow's documented [image decoding and decompression limits](https://pillow.readthedocs.io/en/stable/reference/Image.html), with stricter application limits and pixel re-encoding. This is not OCR, computer vision or automatic damage detection.

## Authorization and history

Every metadata/file route authenticates the session and active organization. Drivers additionally require their active linked profile and current assignment to the trip. Evidence UUID possession alone grants nothing. All four tables force RLS derived through the visible tenant-owned trip; composite references bind evidence/POD/exception to the correct attempt and trip.

GET `/api/v1/evidence/{id}` reauthorizes every request, checks the stored checksum, returns image bytes with no-store/nosniff headers, and exposes no storage path. Owner review, exception resolution, upload and read capabilities are separate. Denying evidence read also removes evidence metadata from attempt responses. No tenant-wide driver POD enumeration endpoint exists.

Uploads cannot overwrite objects. Before attempt submission, an upload may explicitly name `supersedes_id` for active evidence of the same type in the same attempt; original bytes/metadata remain retrievable and marked SUPERSEDED with an audit record. There is one active signature per attempt. Submitted/failed attempts reject uploads and supersession. No ordinary hard-delete or history-edit endpoint exists. Database triggers enforce these boundaries independently of frontend controls.

## API contract

All existing-trip mutations require `expected_version`, using the existing organization write lock; stale/duplicate submissions return 409. Upload authorization precedes body processing and is rechecked after the lock, followed by refreshing the trip version. Requests must carry the existing allowed Origin and authenticated cookies.

| Endpoint | Meaning |
| --- | --- |
| GET `/api/v1/trips/{id}/delivery-attempts?limit=20&offset=0` | Own/permitted trip attempt history, newest first, exact count, policy and trip version |
| POST `/api/v1/trips/{id}/delivery-attempts` | Explicit new attempt; version body |
| GET `/api/v1/delivery-attempts/{id}` | Authorized attempt with POD, exception and permitted evidence metadata |
| POST `/api/v1/delivery-attempts/{id}/evidence` | Raw JPEG/PNG/WebP body; query `expected_version`, `filename`, `evidence_type`, optional `supersedes_id` |
| POST `/api/v1/delivery-attempts/{id}/pod` | Recipient name/role, notes, `driver_confirmed: true`, optional `signature_confirmed`, version |
| POST `/api/v1/delivery-attempts/{id}/exception` | Exception type, notes, version |
| GET `/api/v1/pod/{id}` | Authorized POD metadata |
| POST `/api/v1/pod/{id}/review` | Operator review, version |
| GET `/api/v1/evidence/{id}` | Authorized private image bytes |
| POST `/api/v1/delivery-exceptions/{id}/resolve` | Operator on-site retry authorization, resolution notes, version |

No generic delivery PATCH/DELETE exists. Known but inaccessible IDs return 404; missing capabilities return 403; invalid inputs 422; body too large 413; lifecycle/version conflicts 409.

## Transaction and migration boundaries

Delivery commands explicitly commit before returning success, so deferred constraints and audit errors cannot surface after a successful response has started. POD, successful attempt, trip transition, milestone and audits commit together. Upload bytes are written privately before metadata commit, and rollback removes uncommitted objects. A process/power failure may leave an unreferenced private orphan; it cannot be retrieved through the API. Crash recovery, retention cleanup and combined database/object backup require operator procedures before production. No automatic deletion of submitted evidence is implemented.

Migration `0004_proof_of_delivery` adds four tables and `trips.pod_required`. Existing DELIVERED/COMPLETED/CANCELLED trips are marked legacy without fabricated POD; active existing trips and all newly created trips require POD. Legacy delivered trips may use existing closeout, and the UI labels absent historical evidence. The flag has no client mutation and a database bypass guard. Rollback drops Batch 5 tables/data and the flag while retaining Batch 4 trips/milestones; only isolated test rollback is authorized by the verification workflow. Back up both database and private objects before any real operator-directed migration rollback.

Metadata-only retrieval: `GET /api/v1/evidence/{id}/metadata`; exception detail: `GET /api/v1/delivery-exceptions/{id}`. Both apply the same tenant, permission and driver-owned trip checks as the existing evidence/history routes. Metadata excludes storage keys.
