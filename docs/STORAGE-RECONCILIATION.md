# Evidence reconciliation

Run `python -m fleetpilot.storage_admin reconcile` from apps/api with explicit storage configuration and MIGRATION_DATABASE_URL for the privileged administrative connection. This is a CLI, never a tenant-facing API. `SET row_security=off` ensures a restricted account errors instead of silently inspecting only some tenants.

Report categories: missing object (evidence ID), checksum mismatch (evidence ID), orphan object (hash of internal key), and superseded_retained (evidence ID). Both ACTIVE and SUPERSEDED rows remain legitimate references. Superseded history is not automatically garbage-collected. The tool never deletes objects or rewrites evidence metadata. There is no cleanup switch.

Pause writes for a stable inventory. During normal uploads, a private uncommitted object can temporarily appear orphaned; a failed readiness probe may also leave a zero-prefix object. Investigate and repeat after a grace period. Do not equate an orphan report with permission to delete production data. Any future cleanup needs separate approval, backup, retention review and a second reference check. Malformed object keys or provider failures abort inspection rather than reporting false success.

Snapshot and restore commands are documented in BACKUP-RESTORE.md. Reports are administrative artifacts; protect them and backups outside public web roots.
