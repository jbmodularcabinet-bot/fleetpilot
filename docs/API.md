# Foundation API

Prefix `/api/v1`; same-origin browser cookie authentication. Mutations require `Origin` equal to `WEB_ORIGIN`. No arbitrary organization header is accepted. Organization selection cookies are revalidated against active memberships on every request.

| Method / route | Behavior |
| --- | --- |
| GET `/health` | Liveness, `{"status":"ok"}` |
| GET `/ready` | Database/migration-table availability |
| POST `/api/v1/auth/login` | Form-encoded `username` email and `password`; 204 with session cookie |
| POST `/api/v1/auth/logout` | Revoke session and clear session/organization cookies; 204 |
| GET `/api/v1/me` | Current user, active organization/membership, permissions and own organization choices |
| POST `/api/v1/organization-selection` | Validate and select a membership organization; JSON `organization_id` |
| GET `/api/v1/organizations/{id}` | Read current organization's settings |
| PATCH `/api/v1/organizations/{id}` | Authorized name/legal name/timezone/currency/country update; audited |
| GET `/api/v1/memberships` | Authorized tenant member list, limit 1–100 and offset |
| POST `/api/v1/memberships` | Add already-provisioned account by email/role; audited, 201 |
| PATCH `/api/v1/memberships/{id}` | Role and active status change; audited |
| GET `/api/v1/audit-logs` | Authorized tenant audit list, bounded limit/offset |

Error envelope: `{"error":{"code":"...","message":"...","request_id":"..."}}`. Validation errors never echo submitted passwords or raw payloads. Foreign resource IDs return 404; unauthorized capability/organization context returns 403; absent/expired login returns 401. Duplicate memberships and forbidden self/last-owner changes return 409. Invalid fields return 422; login throttling returns 429 with Retry-After.

Organizations and initial accounts are provisioned through an explicit operator CLI; public organization creation/signup is not exposed. No domain APIs exist.
