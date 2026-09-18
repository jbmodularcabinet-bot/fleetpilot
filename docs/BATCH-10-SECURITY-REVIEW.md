# Batch 10 security review

Scope: engineering source/configuration review and executed local regressions; no independent assessment or remote-production certification. Final results are in BATCH-10-REPORT.md.

## Retained controls

Session-derived tenant context, opaque sessions, explicit capabilities, exact-origin mutation checks and forced PostgreSQL RLS remain unchanged. Driver access follows the linked assigned identity; known UUIDs do not authorize access. Replay receipts recheck current access, share the domain transaction and preserve history. Completed-trip adjustments remain privileged, append-only, reversible and Decimal-based; original financial data and operational closeout remain immutable.

Evidence remains behind authenticated API retrieval. No public upload directory or signed URL exists. Opaque keys, path validation, bounded image decoding/normalization, checksums and conditional object writes remain. Database/object storage compensation is not a distributed transaction; reconciliation and quiesced coherent backups remain necessary.

Production configuration fails closed without HTTPS origin, restricted runtime DB role, shared rate limiting and private S3. The API process receives no migration URL. Local actual HTTPS responses and login flags were verified in .runtime/batch10-https-security.json. Public ingress/proxy forwarding, trusted TLS chains and actual deployed cookies remain UNVERIFIED.

The offline store is identity-scoped and cleared on logout/account change; expired sessions lock sync and retain same-account recovery. Storage acknowledgment follows transaction completion. No guarantee of OS persistence or background execution is made. Physical-device access, encryption at rest and revoked authorization discovery while disconnected remain limitations.

## Findings and disposition

- Documentation discrepancy: DEPLOYMENT-HARDENING.md named readiness revision 0005; actual source and database require 0008_closed_trip_adjustments. Documentation corrected; no behavior change.
- No source or test assertion was modified to obtain green results. Existing security checks are rerun as part of the complete suite.
- Accessible verification is local Windows/Chrome, PostgreSQL and loopback Versity S3 only. No Docker, remote repository/CI, staging, remote provider or monitoring exporter was accessible. These unavailable controls are UNVERIFIED, not failures concealed as passes.
- Local restore invalidated sessions and verified evidence checksums, unauthorized retrieval denial and financial overlay preservation. It is not an offsite recovery/RPO/RTO certification.
- Synthetic quota rejection and compatible update tests are bounded browser experiments, not a guarantee against OS eviction or arbitrary incompatible future upgrades.

Review includes IDOR/BOLA, cross-tenant/driver access, replay authorization, private evidence, immutable audit/history, strict Decimal corrections, unsafe input, session/CORS/CSRF, file/path/MIME boundaries and storage exposure. Final local test outcomes and any remaining release blockers are recorded in the report. Remote IAM, external monitoring delivery, actual devices and independent penetration assessment remain unverified risks.

Final local gate: PASS — 269 backend + 36 frontend + 32 production-browser cases (337 total), zero failures/skips. No unresolved blocker identified in executed scope. Overall CONDITIONAL PASS because real device and remote environment gates are UNVERIFIED.
