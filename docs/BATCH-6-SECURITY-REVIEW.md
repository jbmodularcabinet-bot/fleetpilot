# Batch 6 security review

Scope: application/infrastructure engineering review, real local S3/HTTPS/PostgreSQL tests and regression. Not an independent assessment or remote deployment certification.

## Audit and retained architecture

Read the required Phase 0, Batch 2–5 reports/reviews, lifecycle, POD, exceptions and locked design documentation. Inspected actual settings, auth/session/tenant/RBAC/RLS, evidence models/routes/storage, commit/compensation, migration triggers, request middleware, Next headers/layout, test fixtures, Docker and CI. Source confirms the reported Batch 5 implementation; no discrepancy justifies replacement. The supplied baseline's remaining production limitations were real: local-only evidence, process-local login limiter, DB-only readiness, broad inline script CSP, incomplete recovery/observability/deployment checks.

## Controls and findings

| Concern | Control / verification |
| --- | --- |
| Public objects / UUID or key possession | Application-authorized bytes only; no signed or public URLs; S3 conditional writes, private default ACL; readiness rejects public bucket grants/policies. Real gateway anonymous download denied. Remote-provider policy remains unverified. |
| IDOR/BOLA, tenant and driver boundary | Existing context/capabilities/trip checks and forced RLS unchanged. Batch 5 adversarial suites rerun against actual S3, including known photo/signature/POD/attempt IDs and direct PostgreSQL RLS. |
| Path traversal / filename abuse | Existing strict opaque-key regex and safe local resolution; filenames never select storage destinations; restore validates manifest paths and object keys. |
| MIME spoofing, executable/SVG/malformed/oversized payloads | Existing bounded decoder/pixel normalization retained; ordinary whole-request limits precede parsers, including chunked bodies; evidence uploads preserve authorization before bounded streaming. S3 and local stored reads are bounded. |
| Overwrite / historical tampering | If-None-Match:* conditional S3 put; no fallback overwrites, no ordinary evidence delete; retained superseded metadata/bytes and immutable domain triggers. |
| Partial storage/DB failure | Explicit commit-before-success retained; uncommitted compensation catches cleanup failures without hiding original errors; report-only reconciliation detects leftovers/missing/mismatch. Real S3 outage/timeout and DB failure tests supplement existing local fault tests. |
| Rate-limit bypass | Production requires shared PostgreSQL atomic counters. Session/key rotation does not change peer/category budget. Trusted-proxy configuration is explicit; arbitrary forwarded headers are not read by limiter. Two-process test verifies a shared budget. Limiter failure returns 503. NAT aggregation and infrastructure capacity limits remain operational considerations. |
| Secrets / logs | Allowlisted structured telemetry omits request data, headers, query strings, raw exceptions and provider URLs. Settings validation suppresses input values. SDK secrets come from environment/workload identity. No credentials in images or repository. |
| Sessions / CSRF / CORS | Established hashed opaque DB sessions, exact-origin mutations, active membership, narrow credentialed origins, production Secure/HttpOnly/SameSite=Lax cookies retained. No invented unused signing secret or alternate login. |
| CSP / framing / cache | Request-nonce script CSP, denied framing/object content, no production unsafe-eval/inline scripts; style exception documented. API early rejections receive security headers/request IDs. Production HSTS retained for HTTPS. |
| Backup exposure / restore RLS | Explicit privileged CLI, private snapshots, no ordinary HTTP admin endpoint, validated restore paths/checksums, new disposable resources, real pg_dump/restore, restored-session invalidation to prevent resurrecting revoked cookies, restricted-role API and tenant denial after recovery. Production encryption/retention/offsite ACLs not configured here. |
| Monitoring / readiness | Safe exporter callback boundary; no credentials/provider assumed. Liveness independent of dependencies; readiness fails closed on schema/storage/DB incompatibility. Management probes must stay private and bounded. |

The infrastructure rate table contains only hashed peer/category keys, expiry and counter, not tenant business data. It is intentionally not tenant-owned and cannot expose domain records. Runtime DB credentials remain a trusted server boundary; users never receive SQL credentials. Domain RBAC/RLS and audit immutability were not weakened.

## Dependency assessment

Fresh npm audit and pip-audit against pinned application requirements reported zero known vulnerabilities at execution. pip check and npm tree validation also passed. This is feed-based evidence, not proof of absence or a future guarantee. Boto3 and its added transitive dependencies are pinned; no major upgrade to existing application dependencies was made. MinIO official download returned 410; checksum-verified official Versity 1.8.0 was used for local integration instead.

## Residual risks

No cross-storage distributed transaction: hard crashes can leave private orphans. Reconciliation is report-only; no automatic deletion/retention policy. Quiesced backup has a maintenance window and does not establish production RPO/RTO. Rate counters share database availability/capacity; fixed windows allow boundary bursts, and NAT can aggregate users. No real multi-host load/soak, ingress deployment, production IAM/encryption, monitoring exporter, offsite recovery, container execution/image scan, remote CI or independent penetration test is claimed. Production deployment remains a separate operator-controlled release.

Executed evidence: 216 unique tests passed, including 29 new backend, 1 new frontend and 2 new browser cases; real private S3 workflows, two-process rate sharing, HTTPS restart and complete DB/object restore passed. No unresolved application security blocker was identified in the executed scope. Overall release is CONDITIONAL PASS because Docker/remote deployment verification is incomplete. Final gates are recorded in BATCH-6-REPORT.md. No Batch 7 feature is authorized by this review.
