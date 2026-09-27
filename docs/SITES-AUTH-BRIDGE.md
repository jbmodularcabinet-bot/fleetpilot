# Sites identity bridge

This gate enables only `GET /api/v1/me`. It does not enable Finance or any mutation.

The published Sites dispatcher supplies a stable, site-specific authenticated subject.
Sites signs a 30-second HS256 assertion on the server with issuer, audience, subject,
issued-at, not-before, expiry, random token identifier, and `parent:me` scope. The browser
receives only the authorized context response, never the assertion or signing secret.
Assertions are bounded read-only credentials; replay within their 30-second validity can
repeat the same context read, but cannot create a session or authorize another route.

Parent verifies the signature, exact issuer/audience, timestamps and scope. An operator
enrolls an existing Parent user by setting `users.auth_provider_id` to `sites:` plus the
SHA-256 digest of `issuer + "\n" + subject`. Email, display name, Sites demo roles and
browser-supplied user IDs are not mapping inputs. Enrollment must verify both account
identities; it must never search for a user by email and automatically grant membership.
The current pilot was explicitly enrolled from the authenticated owner Sites session
to its existing Parent pilot-owner account; no user or membership is created by a request.

Parent resolves its configured organization through the existing tenancy code, including
forced PostgreSQL RLS, active user and membership checks. This pilot bridge requires a
current OWNER membership. A conflicting organization cookie is rejected. Role or
membership revocation is checked afresh on every request. Normal password/cookie
authentication remains available. Invalid assertions cannot fall back to a cookie identity.

Parent server configuration: `SITES_BRIDGE_SECRET`, `SITES_BRIDGE_ISSUER`,
`SITES_BRIDGE_AUDIENCE`, `SITES_BRIDGE_ORGANIZATION_ID`. Sites server configuration:
`PARENT_API_BASE_URL`, `PARENT_BRIDGE_ISSUER`, `PARENT_BRIDGE_SECRET`. Store the same
cryptographically random signing secret in both providers' secret configuration.
No secret belongs in source, client bundles, D1, logs or public environment variables.

The Sites proof route is `/parent-connection`, backed by `/api/parent/me`.
Each refresh uses the current dispatcher identity and creates a fresh assertion.
Responses are uncached. Missing or unmapped identity fails closed.

No migration is required: the existing unique `auth_provider_id` column stores the binding.
Disabling the Parent bridge secret revokes all bridge access without affecting password
sessions. Clearing an individual provider binding revokes that account's bridge access.
Keep the exact Sites origin in the existing CORS allowlist.
