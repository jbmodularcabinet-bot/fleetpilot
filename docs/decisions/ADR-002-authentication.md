# ADR-002 — FastAPI Users and opaque database sessions

Status: accepted for Batch 2; revises the audit's proposed OIDC provider.

The user authorized selecting an established solution. Choose FastAPI Users with its SQLAlchemy adapter, password helper and database session strategy. This delivers locally runnable authentication without adding an external identity-provider account or Keycloak service. We do not implement password cryptography or token generation ourselves.

The library verifies Argon2 password hashes and issues random opaque session tokens. An adapter hashes tokens before persistence while preserving the library's expiry and logout lifecycle. Cookies are HttpOnly, SameSite=Lax and Secure in production. All mutation requests require the configured same-origin header. Session expiry is fixed at eight hours by default and can be configured.

Accounts are operator-provisioned; self-registration, recovery, verification email and OTP routes are not exposed. Identity is global, while roles/permissions live on memberships. No role is trusted from a cookie or browser payload. Login clears prior organization selection. Owner/Admin/Manager redirect to dashboard; Driver to driver home; other roles to read-only organization settings.

Tradeoff: FleetPilot hosts password hashes and must operate account recovery/onboarding responsibly. OIDC/SSO remains a later integration through the reserved provider identifier; this is not implemented. Multi-process deployments require a shared edge rate limiter. Password reset and MFA are explicit future security work, not fake links.

Primary references: [FastAPI Users overview](https://fastapi-users.github.io/fastapi-users/latest/configuration/overview/), [SQLAlchemy adapter](https://github.com/fastapi-users/fastapi-users-db-sqlalchemy), [database strategy](https://fastapi-users.github.io/fastapi-users/14.0/configuration/authentication/strategies/database/). Installed implementation and cookie/database interfaces were inspected while integrating.
