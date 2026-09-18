# Driver offline sync architecture

Batch 7 extends the existing driver components and authoritative FastAPI commands. It does not create offline authentication, a second trip state machine on the server, or an owner offline application.

## Data and ownership

IndexedDB `fleetpilot-driver-v1`, schema version 2, has `meta`, `snapshots`, `actions`, and `drafts` stores. The upgrade creates missing stores without deleting existing records. Ownership is the tuple organization ID, authenticated user ID, linked driver ID. Normal UI access checks that tuple and a 12-hour offline lease from the last successful authenticated identity request. Snapshots separately expire after 12 hours. A materially backward device clock locks access. This is a device-local convenience policy, not cryptographic offline authentication: browser/device administrators and XSS can inspect or alter storage.

Only authorized driver-trip projections, viewed milestone/delivery history, minimal display identity, pending commands and local evidence are stored. No owner master-data lists, tenant-wide audit history, credentials, session tokens or private server evidence downloads enter the offline cache. Assigned-list pages also save their trip projections; records/history not downloaded while online display an explicit unavailable message offline. Viewing a trip online prepares its full offline workflow.

Local evidence uses structured-clone File/Blob records, not localStorage/base64. Draft fields autosave after 300ms; Saved locally appears only after transaction completion. Submission atomically persists the dependent queue. Limits: 100 pending commands and 40 MiB queued binary evidence; up to 10 selected draft photos, each nonempty and <=5 MiB / 16 megapixels. MIME/extension, magic bytes and browser decode are checked locally; the existing stricter server normalization and 12-file history limit remain authoritative. No compression or image recognition was added.

## Causal queue and authoritative state

Each command has a stable UUID key, ownership tuple, trip, semantic command, expected version, local capture time, sequence, status, retry information and optional attempt dependency/Blob. Enqueue serializes in an IndexedDB readwrite transaction and rejects overlapping versions from another tab. The UI projects the next local milestone only to permit subsequent capture, with an explicit pending notice. The status badge stays server-confirmed. Local POD never marks the trip DELIVERED.

The central engine uses Web Locks across tabs and the service worker. Calls wait their turn rather than silently skipping a busy lock, so work enqueued during an existing drain is processed promptly by the waiting call. It authenticates, verifies the current driver identity, refreshes each trip from the server, then submits in persisted order. Different resources/tenants cannot be selected through untrusted ownership fields. Delivery chains create an attempt, resolve its accepted ID, upload each image, and submit POD/exception. An accepted attempt result survives a lost response through server replay. Expected versions are never silently rebased. One conflicted trip blocks its remaining commands; other trips may proceed.

Sync triggers: app startup, reconnect, foreground focus, manual retry, and a 30-second visible-page check while pending work exists. Background Sync registers when available and runs the same dependency-free engine. Unsupported browsers retain foreground/manual behavior. Automatic transient retries persist exponential delays starting at 5 seconds, capped at 5 minutes, with at most 8 attempts; exhausted work requires manual retry. Authentication failures lock local access and retain work for same-account login. Validation/permission errors require attention; conflicts require operator review and explicit discard rather than forced application.

## Recovery and limitations

Successful uploads release queue Blob copies; final POD/exception clears its draft. Logout warns about pending actions/drafts, allows cancellation, and clears all local stores after server logout succeeds. Signing back into the same verified identity preserves queued work; changing identity clears it after the app's explicit warning. Offline logout does not claim server session revocation. Server revocation/assignment changes cannot be known while disconnected; reconnect rechecks them before mutation or replay.

Browser storage is not encrypted at rest and can be evicted by the platform. A storage failure does not produce a Saved locally acknowledgement. Device loss before sync can lose pending evidence; server backups cannot recover unsynced device data. No guaranteed OS background execution, physical-device support, production deployment, GPS or Batch 8 scope is claimed.
