# HABI Portfolio Web SaaS Reference Architecture

FleetPilot is the reference implementation for engineering discipline, security, release controls, and verification. Product-specific domain logic must not be copied into unrelated SaaS products.

## Reusable layers
- Web: Next.js / React / TypeScript, responsive/PWA shell, shared design tokens, accessibility.
- API: explicit service boundary, typed contracts, validation, request IDs, safe structured logs.
- Identity: users, organizations, memberships, roles, permissions, session lifecycle.
- Tenancy: explicit tenant context, server-side authorization, database-enforced row isolation.
- Data: PostgreSQL migrations, constraints, indexes, immutable/audited records where required.
- Storage: private object storage, tenant-scoped access, checksum/evidence validation where applicable.
- Security: RBAC, RLS, CSRF/origin controls, rate limits, body limits, secure cookies, CSP/HSTS.
- Operations: health/readiness, backups, restore drills, monitoring, release evidence, rollback plan.
- Quality: unit, integration, browser, migration, security, visual, build, and regression gates.

## Supabase adaptation
For portfolio products that use Supabase, preserve the same control objectives: organization-scoped tenancy, RLS on every exposed table, authorization data outside user-editable metadata, private storage policies, migration discipline, typed clients, auditability, and independent production verification.

Do not force FleetPilot itself onto Supabase solely for standardization. FleetPilot's verified FastAPI/PostgreSQL architecture remains authoritative unless a separately approved migration project proves parity and rollback.

## Delivery pattern
ChatGPT defines controlled batches and acceptance gates. Codex/Astra performs repository implementation and automated verification. Remote Desktop Commander performs independent runtime/browser/device checks. Production release requires evidence from committed code, remote CI, staging, security, recovery, and deployment gates.