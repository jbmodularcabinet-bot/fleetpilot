# Idempotency and conflicts

Migration `0006_driver_sync` adds immutable `driver_sync_commands` receipts. The primary key is `(organization_id, actor_user_id, idempotency_key)`. Composite foreign keys bind driver/trip to the organization. Forced RLS limits reads/inserts to the current organization AND actor. UPDATE/DELETE have no policies and an immutable trigger. Existing `Trip.version`, organization serialization, RBAC, RLS and domain history guards are retained.

Driver-only endpoints:

- `GET /api/v1/driver/offline-identity`
- `POST /api/v1/driver/sync/{trip_id}/{transition|attempt|pod|exception}`
- `POST /api/v1/driver/sync/{trip_id}/evidence`

Every mutation requires `Idempotency-Key` UUID, expected version and timezone-aware client capture time. JSON accepts only the explicit envelope and strict existing command fields. Evidence remains a bounded raw-image request, authorized before its body is read. Organization and driver identities come exclusively from the current authenticated tenant context and linked active profile.

Within the existing organization lock: recheck permission and assigned-trip access; hash canonical command/resource/payload/version/time (plus raw content hash, MIME and filename for evidence); look up the immutable receipt. Same key and identical request returns ALREADY_APPLIED with the original result. Changed payload/key reuse conflicts. A known key never bypasses current authentication, permissions, assignment or tenant checks. Different actor keys cannot read another actor's result.

For a new key, execute the existing domain command and insert the receipt in the SAME transaction. Delivery's normal explicit commit is deferred only inside this server-owned sync wrapper. Commit occurs before success is returned. Audit/constraint failure rolls back both command and receipt; storage compensation remains in the existing request transaction. No process-local deduplication state exists. Stable replay survives API process restart and a response lost after commit.

Client time is retained as `occurred_at_client`; database `received_at_server` and existing milestone/audit timestamps are authoritative. More than 24 hours of absolute clock difference is flagged `clock_suspect`; the client clock never rewrites history. No historical event correction was introduced.

Stale versions and invalid state transitions are 409 conflicts. The client never assumes a similar current state means its command was accepted: only its matching receipt proves that. 401 locks sync, 403/404 deny access, 422/413 require correction, network/429/5xx failures retry with bounded backoff. Generic UI messages omit stack traces and raw provider details. Accepted server history is preserved when the user explicitly discards local unresolved work.
