# Batch 11 security review

Date: 17 September 2026. Scope: maintenance schedules/work orders/costs, downtime/dispatch, driver defects, private images and shared offline receipts. This is an implementation review and local automated assessment, not an independent penetration test or deployed certification.

## Controls and findings

| Area | Control / review outcome |
| --- | --- |
| IDOR/BOLA/tenant ownership | API context scopes every lookup; organization-composite foreign keys; forced RLS on all six new tables; known foreign UUIDs return safe denial. Tenant-filtered lists/counts/search. |
| Driver ownership | Server derives active linked driver, validates current assignment or exact own nonterminal trip; no client driver_id. Own-report/evidence policy and API checks prevent same-tenant cross-driver access. New uploads reauthorize current assignment. |
| RBAC | OWNER/ADMIN/MANAGER/MAINTENANCE receive maintenance capabilities; DRIVER receives only own defect capabilities. DISPATCHER/ACCOUNTING have no maintenance mutation capability. Restrictive permission overrides remain authoritative, including evidence byte access. |
| Workflow / availability | Explicit action graph, expected version, organization write lock; DB terminal/history guards. Maintenance/inactive assignment blocked by existing eligibility checks plus DB trigger. Active downtime cannot be cleared by master unassignment, reactivation or direct status update. |
| Overlapping downtime | Completion queries other active blockers; preserves INACTIVE; returns ASSIGNED only for current master assignment, otherwise AVAILABLE. Starting downtime is rejected during an operational trip. |
| Money | Strict decimal strings, bounded Decimal/NUMERIC values, server rounded multiplication and totals; client totals forbidden; no maintenance-to-trip expense writes. |
| Odometer | Maximum trusted owner/reviewed-fuel/completed-maintenance reading. Unreviewed fuel does not advance schedules. Completion below the trusted floor rejected in API and DB. No silent historical odometer correction. |
| Mass assignment / injection | Extra fields forbidden in schemas; bound query parameters; domain/action allowlists; fixed sorting. Table/column interpolations use internal allowlists, never client SQL. |
| Files | Shared 5 MiB / 16-million-pixel JPEG/PNG/WebP validator; decoded and normalized content; random opaque keys; exclusive/private storage write; checksum read; no public upload mount. File names are display metadata, not filesystem paths. |
| Evidence authorization | Parent/tenant/permission checked before streaming or read. Staff evidence.read denial is enforced even when defect.read is granted. Bytes have private,no-store, nosniff and fixed safe disposition. |
| Tampering | Cost/evidence/events append-only; original defect fields immutable; terminal work immutable; no DELETE policy; platform immutable audit retained. Closed maintenance corrections explicitly deferred. |
| Offline/idempotency | Existing IndexedDB account/session isolation and queue limits; durable actor/tenant/key/hash receipts; report and dependent photo replay exactly once. Authorization precedes replay; changed payload conflicts. |
| Transaction failure | Work/vehicle/schedule/defect/events/audit/receipt in one DB transaction. Storage uses existing uncommitted-object cleanup. Synthetic audit failure rolls back the work and receipt. |
| Session/privilege | Existing cookie authentication, CSRF/origin/rate limits unchanged. Driver cannot gain owner functions through direct endpoints. No secrets or binary evidence written to audit. |

Review identified and fixed: master unassignment could otherwise clear maintenance status; active-blocker reactivation needed an explicit 409; evidence.read restrictive overrides needed enforcement on defect images; attention rows needed authoritative statuses; server/model fields needed MAINTENANCE support. No unrelated trip state-machine transitions were weakened.

## Evidence and limits

Backend tests exercise foreign tenant API reads/writes/uploads, all six populated RLS tables, driver boundaries, role denials, restrictive evidence permissions, immutable costs/closed work, direct vehicle-status tampering, exact money, reviewed fuel, concurrent report/photo keys, file attacks and audit rollback. Browser automation exercises persistent offline report/photo, committed-response loss, authoritative replay and repair resolution. Final execution totals and outcomes are recorded in BATCH-11-REPORT.md.

RLS supplies tenant/role/own-record defense in depth; restrictive per-membership capability overrides are enforced by API authorization. The runtime database role is not exposed as an end-user connection. Migration/backup superuser credentials remain trusted infrastructure, not an adversarial runtime identity.

Production remote storage/IAM, devices/Safari, external monitoring, remote CI, deployed isolation and independent security testing remain UNVERIFIED. Local private storage results do not certify remote access policies. Browser storage eviction and separate photo synchronization remain known limits. Maintenance evidence is included in storage reconciliation/backup enumeration; a new remote restore drill was not performed.

Final local outcome: no unresolved release-blocking finding identified. Full backend 307/307 followed by final 39/39 maintenance tests covers 308 unique backend cases; full browser 34/34 plus final two maintenance golden rechecks passed. Total with 41 frontend cases is 383 distinct passing tests. Repeated checks are not counted twice. This is not independent security certification.
