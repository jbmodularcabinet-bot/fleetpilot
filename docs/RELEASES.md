# Releases

## 0.2.0 — Batch 2 foundation (2026-09-16)

Foundation-only completion. This is not a production release of the full FleetPilot product.

- npm monorepo with Next.js/React/strict TypeScript/Tailwind/Inter and FastAPI.
- Real PostgreSQL migration, separate runtime/migration roles, forced tenant RLS and append-only audit records.
- FastAPI Users login/logout, hashed opaque sessions, expiry, origin protection and per-process login throttling.
- Organization selection/settings and seven membership roles with centralized server permission checks.
- Persisted member additions, role changes and deactivation; no public invitations or signup.
- Approved owner and driver empty shells, functioning settings/profile, disabled future modules, shared tokens and components.
- Explicit synthetic development seeding, operator provisioning, pinned dependencies, local service tooling, Docker alternative and CI definition.
- 42 API/unit/integration tests, 4 web tests, 8 browser tests; migration roundtrip, lint/typecheck/build/startup passed.

Known limitations: screenshot-backed logo, initial manifest without installation/offline claims, no account recovery/MFA/OTP/email invitations, per-process rate limiting, no external monitoring or deployment verification. The production CSP still permits inline scripts/styles; nonce hardening remains release work. Future operational modules and business rules are not implemented.

Phase 0 was preserved. No Batch 3 work was started. Recommended next scope: customer/vehicle/driver-domain CRUD with tenant isolation, permissions and audits.
