# Permissions

Permissions are resolved centrally in `apps/api/fleetpilot/permissions.py`. Unknown roles have no permissions. `permissions_json` currently supports only a `deny` list; UI/API mutation of custom grants is not exposed.

| Capability | Owner | Admin | Manager | Driver | Dispatcher / Accounting / Maintenance |
| --- | --- | --- | --- | --- | --- |
| organization.read | Yes | Yes | Yes | Yes | Yes |
| organization.manage | Yes | Yes | No | No | No |
| users.read | Yes | Yes | Yes | No | No |
| users.manage | Yes | Yes, restricted | No | No | No |
| audit.read | Yes | Yes | Yes | No | No |
| owner_dashboard.view | Yes | Yes | Yes | No | No |
| driver_app.view | No | No | No | Yes | No |

Only owners can grant or modify Owner/Admin access. Users cannot demote or deactivate themselves through the UI/API. An organization must retain an active owner. Inactive memberships are rejected at the next request even if their login session has not expired. Inactive users and suspended organizations are rejected too.

After login, Owner/Admin/Manager land on `/dashboard`, Driver on `/driver`, and the remaining roles on read-only `/settings/organization`. Drivers cannot render the desktop administration shell; direct links return them to `/driver`. API driver access to organization user administration is denied. Permission hiding is supplementary only.

No future dispatch, maintenance, accounting or operational permissions are guessed in this batch. When implementing those domains, expand the matrix and add both positive and negative API tests.
