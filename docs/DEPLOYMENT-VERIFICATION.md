# Batch 10 deployment verification

Verification date: 17 September 2026. Scope: existing local configuration and disposable verification resources only.

| Target | Availability and result |
| --- | --- |
| Docker | UNVERIFIED: no docker command or executable at the standard Docker Desktop path. Dockerfiles/compose reviewed only. No image build or container smoke run. |
| Remote CI | UNVERIFIED: git remote is empty; no accessible run/provider integration. Existing Foundation checks workflow reviewed; no remote run ID. |
| Staging/production deployment | UNVERIFIED: no configured accessible target. No public deployment, certificate issuance or infrastructure replacement attempted. |
| Remote object storage | UNVERIFIED / NOT CONFIGURED. Current development defaults to local storage; accessible integration gateway is loopback Versity only. |
| External monitoring | NOT CONFIGURED / UNVERIFIED. hardening.monitor is an unset optional exporter; no provider delivery claimed. |
| Remote backup/restore | UNVERIFIED: no disposable remote environment. |
| Deployed tenant/cross-driver attacks | UNVERIFIED: local API/direct PostgreSQL regressions do not certify remote ingress/runtime. |
| Staging load | UNVERIFIED: no staging endpoint. Existing 120-request local drill is reported separately, not the suggested 500-request staging exercise. |

## Source review

Existing non-root API/web Dockerfiles, standalone Next build, private compose services, external env injection, runtime migration-credential removal, read-only API root, dropped capabilities and loopback ingress retained. .dockerignore excludes local credentials/runtime data. TLS ingress, trusted proxies, image provenance/digests and deployment secrets require real environment verification. Static source review cannot prove image contents or startup.

CI includes migration roundtrip, PostgreSQL, private local S3 gateway, backend/frontend/browser, lint, Python/dependency/type checks and production build. No repository remote is configured, so no job was triggered.

Readiness source requires 0008_closed_trip_adjustments. DEPLOYMENT-HARDENING.md still named 0005; corrected that stale reference without changing source behavior. All tenant domain tables inspected have forced RLS; global auth/session/version/rate-counter tables retain their established distinct ownership model.

## Executed local environment

Production standalone frontend build and browser results appear in BATCH-10-REPORT.md. The existing HTTPS/S3 drill was rerun with DRILL_BATCH9=1 to include expenses and adjustments. Its directory retains the tool's batch9 prefix: .runtime/batch9-drill-407289994841/. This is a NEW Batch 10 execution, not reuse of Batch 9 results.

Fresh synthetic database and bucket, HTTPS API restart, quiesced PostgreSQL dump, fresh restore database/bucket, session invalidation, fresh login and evidence checksum/retrieval all passed. Restored: one completed trip, 14 milestones, 35 audit rows, one attempt/POD, two delivery objects, three expenses/revisions, one receipt, one adjustment and one effective projection. Original toll 300 / effective toll 350 / total 3450 preserved. Anonymous and foreign-tenant evidence denial passed. No live database was rolled back or restored over.

Additional real local HTTPS probe passed health and readiness, CSP, nosniff, no-referrer, denied frame/camera/microphone/geolocation API policies, HSTS and actual login cookie Secure/HttpOnly/SameSite=Lax flags. Evidence: .runtime/batch10-https-security.json. A one-day test certificate with client verify=False is used only for this disposable loopback test; public certificate trust and ingress remain UNVERIFIED.

Local load: 120 requests, concurrency 4, zero errors (0%), aggregate p50 99.07 ms / p95 370.98 ms; login p95 1054.86 ms. Endpoint mix: 20 each login, trips, dispatch, trip detail, expense summary and fuel history. p99 and CPU/memory were not captured; timeouts were not separately categorized (zero total errors). No evidence-endpoint load run or production capacity claim. Raw artifact: .runtime/batch9-drill-407289994841/load-result.json.
