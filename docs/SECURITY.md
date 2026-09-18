# Security foundation and deployment boundary

Implemented controls:

- FastAPI Users credential verification and opaque database sessions; Argon2 password hashing through the maintained library.
- Session token hashes in PostgreSQL; HttpOnly SameSite=Lax cookies, production Secure flag, expiry and logout revocation.
- Login and settings forms use POST and do not become interactive before hydration. Credentials must never appear in URLs. Login has a no-JavaScript regression test.
- Exact configured Origin required on every mutation, including login/logout; explicit credentialed CORS allowlist.
- Membership revalidation, central role permissions, explicit tenant filters and forced PostgreSQL row security.
- Restricted runtime database role; no public signup, global user directory, superuser API or arbitrary permission grants.
- Validated organization fields, role enum and duplicate memberships; changes and audit records in one transaction.
- Immutable audit records, bounded pagination, no payload/token/password logging, request IDs and generic internal errors.
- Local random secrets in ignored files; opt-in development seeds prohibited in production.
- Local services bind loopback; frontend includes frame denial, MIME sniffing protection, a restrictive resource-origin policy and disabled camera/microphone/location permissions for this batch.

Production prerequisites:

1. Configure HTTPS, secure origin, private API/database networking, a least-privileged runtime DB connection and a separately held migration/operator connection. Never give the API migration credentials in its deployed environment.
2. Configure proxy trust explicitly. Do not trust arbitrary forwarded client addresses. Add a shared ingress rate limiter before running multiple API processes; the current 10 login attempts/minute limiter is per-process and resets on restart.
3. Configure backup/restore, log retention, external error monitoring and alerting. Structured logs and readiness checks alone are not an incident-response system.
4. Plan account provisioning/recovery before onboarding customers. Email invitations, self-service reset, MFA and phone OTP are not shipped. An operator command provisions initial accounts without echoing passwords; it does not reset existing credentials.
5. Tighten CSP to per-response nonces before production release. Current Next-compatible policy allows inline scripts/styles; eval is needed only for development and is removed from production configuration. No third-party scripts are loaded.
6. Replace screenshot-backed brand artwork with original approved assets when supplied; add approved PWA icons and verify installation. There is no service worker or offline data cache in this batch.

FastAPI's `is_superuser` flag is not used for organization authorization and is false for provisioned users. Global identity/session tables are not RLS tenant records; only internal authentication logic may query them broadly. Future user APIs must preserve the membership-scoped pattern.

Test fixtures intentionally use synthetic accounts. Ignored browser traces can still contain fixture credentials; treat traces as private local test artifacts, rotate disposable credentials if traces are shared, and do not attach raw traces to public tickets. No real credential is committed.

This document describes foundation controls, not a claim that the full product is production ready or independently security audited.
