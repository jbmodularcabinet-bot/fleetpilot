# Database and evidence recovery

Database backup alone is not a complete FleetPilot backup. Preserve schema, users/memberships, tenant data, trip/milestone history, audit records, delivery attempts/POD/exceptions, evidence metadata AND the referenced evidence bytes, including superseded objects.

## Quiesced backup procedure

1. Put ingress into maintenance mode and stop mutation-capable API workers/jobs. Confirm no in-flight uploads remain. Record application revision and Alembic head.
2. With a dedicated privileged backup account, run PostgreSQL `pg_dump --format=custom --no-owner --file /private/backup/database.dump --dbname fleetpilot`. Supply host/user/password through protected PG environment/pgpass, not command-line connection strings. Do not use the restricted runtime account: RLS can prevent a full dump.
3. With matching storage configuration and privileged MIGRATION_DATABASE_URL, run `python -m fleetpilot.storage_admin snapshot --directory /private/backup/objects`. Destination must be new. This copies every referenced object, verifies its SHA-256 and writes a private manifest. Any error invalidates this backup set.
4. Run report-only reconciliation. Record backup checksums and timestamp. Protect backup files with restrictive ACLs and encrypted off-host storage, with separately secured keys. Backups contain personal evidence and authentication hashes. Restore testing must not expose real customer data publicly.
5. Resume application writes only after coherent capture. Define retention/RPO/RTO with the deployment owner; no unconfigured retention promise is made here.

## Restore procedure

Restore into a NEW, empty disposable database and a NEW private bucket, with production traffic isolated. Provision a NOSUPERUSER/NOBYPASSRLS runtime role and an independent migration role first. Use `pg_restore --exit-on-error --no-owner --dbname disposable_database database.dump`, retaining grants or deliberately reprovisioning them. Do not run --clean against an existing environment.

Configure the new bucket, then run `python -m fleetpilot.storage_admin restore-objects --directory /private/backup/objects --confirm-restore`. Existing identical objects are accepted; different bytes are never overwritten. Manifest paths and object keys are validated, and every file checksum is verified. Before reopening traffic, invalidate all restored auth_sessions through the privileged restore connection: a snapshot can contain sessions revoked after backup. Require fresh login; do not revive old cookies. The automated drill performs this step and asserts zero restored sessions before starting the API. Run migrations to the compatible application head and reconciliation, then start the restricted-role API. Verify login, completed trip, POD/review, attempts, photos/signature, milestones, audits and denied foreign-tenant access before routing traffic.

`scripts/hardening-drill.py` automates a synthetic local drill. It creates randomly named fleetpilot_drill_* and fleetpilot_restore_* databases and distinct fp-drill-*/fp-restore-* buckets. It never resets developer/test databases and never drops existing databases. It starts an HTTPS API using a one-day local certificate, records driver POD, reviews/completes, restarts, quiesces, runs real pg_dump/pg_restore, restores binary objects to another private bucket and verifies checksums, counts, login and tenant denial after startup. Test-only HTTP S3 is loopback; HTTPS certificate verification is disabled only in that synthetic client. Artifacts/keys are ignored under .runtime and require local access control. Disposable resources are retained for inspection and need explicit subsequent cleanup.

PG_BIN points to matching PostgreSQL client tools; the local Windows drill used official EDB PostgreSQL 18.6 client tools against PostgreSQL 18.4. The drill also needs the test gateway credentials at .runtime/s3-test.json and cryptography for its disposable TLS certificate.

## Supported versus configured versus verified

Portable database dump + object snapshot/restore is supported. Local executed drill outcomes are in BATCH-6-REPORT.md. Remote scheduled backup, encrypted off-site destination, bucket versioning, replication, point-in-time recovery, retention lifecycle, production credentials, production restore and RPO/RTO are NOT CONFIGURED / UNVERIFIED. Versioning/replication can supplement the portable snapshot but must be configured and tested independently; no paid feature is assumed.
