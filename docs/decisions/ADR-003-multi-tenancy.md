# ADR-003 — Validated tenant context plus forced RLS

Status: accepted for Batch 2.

Application requests resolve a verified user, active membership and active organization before creating TenantContext. Repository constructors require that context and still add explicit organization filters. An arbitrary organization cookie is only a selection request, never authorization.

PostgreSQL policies restrict tenant rows using transaction-local context. Membership discovery permits only the current user's membership rows before an organization is chosen. FORCE ROW LEVEL SECURITY is enabled for organizations, memberships and audit logs. Runtime connections cannot be superuser/BYPASSRLS and do not own schema objects. User/session infrastructure remains global and is not exposed as a global API.

Use one database rather than per-tenant schemas at this scale. This requires discipline at authentication/bootstrap boundaries and future job/cache/file integrations. Tests must exercise direct SQL under the runtime role as well as HTTP foreign-ID attacks. A PostgreSQL administrator remains a trusted privileged operator.

Primary reference: [PostgreSQL row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html). In particular, owner/superuser bypass rules motivated the separate runtime role and forced policies.
