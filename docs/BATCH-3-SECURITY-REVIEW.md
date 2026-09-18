# Batch 3 security review

Scope: customer, vehicle, driver and vehicle/driver assignment APIs/UI, migration and integration boundaries with Batch 2. This is a source review plus local adversarial testing, not an external penetration-test certification.

## Controls reviewed

| Threat                            | Control and verification                                                                                                                                                                                                                                                                                                                                                                   |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| IDOR / BOLA                       | Every route resolves an authenticated active tenant context; identifiers are UUID-validated; lookups include organization ownership and return 404 for foreign IDs. Driver-wide APIs return 403.                                                                                                                                                                                           |
| Cross-tenant leakage              | All four tables ENABLE and FORCE RLS. Runtime role has no superuser/BYPASSRLS privileges. SELECT/INSERT/UPDATE policies require transaction-local organization context; missing context returns no rows. Application search/count/list queries also include ownership.                                                                                                                     |
| Foreign assignments               | Composite foreign keys reference `(organization_id, vehicle_id)` and `(organization_id, driver_id)`. Application resolves both records in the current tenant before assignment.                                                                                                                                                                                                            |
| Duplicate assignments / races     | Partial unique indexes independently enforce one current assignment per vehicle and per driver. Organization write locks serialize mutations; current access is checked again after waiting. Concurrent requests are tested.                                                                                                                                                               |
| Permission escalation             | Central Batch 2 permission map extended with explicit read/create/update/deactivate and assignment permissions. All mutation paths enforce them server-side. Membership deny overrides remain restrictive. Account linking additionally requires `users.manage` and an existing active same-tenant DRIVER membership. Secondary permissions are rechecked from refreshed membership state. |
| Authentication identity confusion | Driver is a separate domain record. Nullable unique tenant/user link and composite membership FK allow profiles before login provisioning; profiles do not create users or permissions.                                                                                                                                                                                                    |
| Mass assignment                   | Pydantic input allowlists forbid extra fields. Organization, actor, record IDs, derived status, assignment timestamps and lifecycle flags are controlled by the server. No arbitrary setattr keys come from raw request bodies.                                                                                                                                                            |
| Unsafe filtering / SQL injection  | SQLAlchemy bound values; hardcoded sort maps; bounded pagination/search; literal escaping of `%`, `_` and backslashes. No raw client SQL identifiers or clauses.                                                                                                                                                                                                                           |
| History / audit tampering         | No DELETE routes/policies. Assignment trigger only allows a current row to be closed once, preserving all other fields. Ended history cannot reopen/change. Batch 2 immutable audit trigger retained. Audit and record changes use the same transaction.                                                                                                                                   |
| Secret / personal-data logging    | Audit metadata contains business field names, lifecycle states and assignment IDs. No passwords, raw session tokens, credentials or full driver contact/license values are logged in change metadata. Driver self-view omits owner notes and other drivers.                                                                                                                                |
| Session / CSRF bypass             | All new endpoints reuse Batch 2 active-user/session and tenant dependencies. Existing mutation-origin middleware remains in force. Browser hiding is not an authorization control.                                                                                                                                                                                                         |

## Role matrix

| Role          | Customers | Vehicles | Drivers                  | Assignments              | Link authentication account |
| ------------- | --------- | -------- | ------------------------ | ------------------------ | --------------------------- |
| OWNER / ADMIN | Manage    | Manage   | Manage                   | Manage                   | Yes                         |
| MANAGER       | Manage    | Manage   | Manage                   | Manage                   | No                          |
| DISPATCHER    | Read      | Read     | Read                     | Read                     | No                          |
| ACCOUNTING    | Read      | None     | None                     | None                     | No                          |
| MAINTENANCE   | None      | Read     | None                     | None                     | No                          |
| DRIVER        | None      | None     | Own limited profile only | Own current vehicle only | No                          |

Manage means create/read/update/deactivate/reactivate; assignments use explicit assign/unassign. Restrictive membership overrides can remove any listed access. `vehicles.assign_driver` and `assignments.manage` are both required.

## Review findings and fixes

- Revalidated secondary account-linking/assignment permissions after obtaining the write lock, closing a possible stale-permission window during concurrent membership changes.
- Enforced capacity/unit pairing in both request validation and database checks, including SQL NULL semantics.
- Preserved immutable assignment fields and explicit close-only updates at database level, independently of API validation.
- Kept status vocabulary conservative: AVAILABLE/ASSIGNED/INACTIVE vehicles; UNASSIGNED/ASSIGNED/INACTIVE driver assignment state. No IN_TRANSIT, maintenance workflow, compliance determination or trip behavior is implied.
- Confirmed historical Phase 0 and Batch 2 reports were not rewritten as current claims.

## Evidence and residual risks

Final execution outcomes are recorded in [BATCH-3-REPORT.md](BATCH-3-REPORT.md). Tests include two populated tenants, foreign direct IDs, list/search/count/mutation attacks, direct restricted-role SQL, composite references, current-assignment uniqueness, closed-history tampering, audit immutability, role matrix, restrictive overrides and session boundaries.

No unresolved release-blocking issue was found in the reviewed Batch 3 code. This statement remains subject to the report's final verification status.

Inherited production risks remain: HTTPS/ingress deployment, shared rate limiting (current limiter is per process), nonce-based CSP hardening, backup/restore drills, monitoring and operator account lifecycle. Database runtime credentials remain a trusted server-side boundary; they must never be distributed to browsers/drivers. Production deployment, Docker-host execution, external penetration testing, load/soak testing and a fresh online vulnerability-feed assessment are UNVERIFIED. Local dependency consistency checks do not establish absence of vulnerabilities.

Assignment history and audit tables intentionally have no ordinary retention deletion path. Any future retention/migration process needs a separately reviewed administrative policy. Organization-level write locking favors integrity at this batch's scale; production contention and search indexing should be measured before high-volume rollout.
