# Architecture — Batch 2

FleetPilot is a monorepo with a Next.js 16 App Router frontend and a FastAPI backend. PostgreSQL 18 is authoritative for identities, organizations, memberships, audit logs, and sessions. Future operational domains are absent.

Browser requests use the web origin. Next.js proxies `/api/*` to an explicitly configured internal API. Server components forward cookies to `/api/v1/me` with `cache: no-store`; protected pages render only after server authorization. Authentication and organization changes deliberately perform full navigation to discard cached client views.

FastAPI Users handles credential verification with Argon2 through its password helper, random opaque sessions, expiry and logout. An adapter stores SHA-256 digests of session tokens. The browser receives an HttpOnly SameSite=Lax cookie, Secure in production. Password and reset/invitation workflows are not custom-built; self-service registration, reset, verification and token-management routes are not exposed.

Every application endpoint resolves an active user, active organization and active membership. Identity/bootstrap requests may enumerate only that user's own memberships. A transaction-local PostgreSQL tenant setting is populated only after membership verification. Tenant repositories require `TenantContext`, and explicit filters are reinforced by forced row-level policies. Identity and session tables are global authentication infrastructure and have no public listing endpoints.

Organization settings and membership changes commit together with audit rows. Membership administration locks the organization before changing access, rejects owner/admin escalation by admins, prevents self-demotion/deactivation and protects the final active owner. Admin is an organization role, not a platform superuser.

Shared packages contain tokens/components, web DTOs, display permission helpers and strict TypeScript configuration. Server permissions remain in one API module. No shared package claims to enforce authorization in the browser.

The API has liveness/readiness endpoints, request IDs, structured completion/error logs without payloads, and consistent error responses. Current rate limiting is per API process. Production requires an ingress-wide limiter when scaling to multiple workers. No worker, storage, GPS, AI or operational background job is implemented in this batch.

See [authentication ADR](decisions/ADR-002-authentication.md) and [tenancy ADR](decisions/ADR-003-multi-tenancy.md).
