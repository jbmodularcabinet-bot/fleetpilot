# Deployment hardening — Batch 6

Architecture remains Next.js/React/Tailwind + FastAPI/SQLAlchemy/PostgreSQL, existing same-origin session authentication, centralized capabilities and forced RLS. No trips, delivery policy or UI redesign.

## Environment and startup

Production requires ENVIRONMENT=production, PostgreSQL asyncpg DATABASE_URL with explicit credentials, a single HTTPS WEB_ORIGIN, STORAGE_BACKEND=s3 and RATE_LIMIT_BACKEND=postgres. Configure S3 as in PRODUCTION-STORAGE.md. Secure/HttpOnly/SameSite=Lax cookies are derived from production mode. Opaque hashed database sessions do not use a SESSION_SECRET; no unused secret setting was invented. The API rejects superuser/BYPASSRLS runtime roles. Migration credentials must not be available to public-facing application containers; run migrations as a separate administrative job. Synthetic seed refuses production mode.

Liveness `/health` checks process availability only. `/ready` checks current migration revision `0013_legacy_review_guards` (Batch 15 hardening head), DB, shared limiter table and private storage read/write/delete capability. Dependency failure returns generic 503 without provider details. Keep readiness on a private management network; probes perform real object IO and should run no more frequently than every 30 seconds. External monitoring is NOT CONFIGURED. `hardening.monitor` is an optional exporter boundary receiving only safe allowlisted records; it receives no raw exceptions, headers, bodies, URLs/queries or binary content.

## Request boundary and rate limits

Production counters are atomic PostgreSQL upserts, shared across application instances and independent of business transactions. No tenant business data is stored: only hashed network/category keys, expiry and count. Fixed windows begin on the first request and last 60 seconds. Defaults per peer: auth 10, uploads 30, evidence access 120, other mutations 120. POD, exceptions, review, resolution and all other mutations are covered. A 429 includes Retry-After:60; limiter storage failures fail closed with 503. Expired counters are removed in bounded batches. Memory mode remains for development/test only and production startup rejects it.

Identity is the trusted ASGI client address, never a request-supplied account/session/key. This prevents cookie rotation from evading a limit but can aggregate users behind NAT. Configure the ingress and Uvicorn trusted proxy allowlist explicitly; never trust arbitrary X-Forwarded-For or '*'. Direct API access must be private. Without trusted ingress forwarding, requests safely share the proxy's limit, which may cause false throttling. These are abuse controls, not volumetric DDoS protection or per-tenant billing quotas.

Application bounds: 64 KiB ordinary mutation bodies, 5 MiB evidence bodies, including chunked input, before parsers/decoders. Ordinary bodies are bounded in middleware. Evidence uploads retain the existing route authorization before streaming; middleware checks declared length and the route enforces the streaming byte limit after permission/ownership checks. Existing image/file-count limits remain. Supplied nginx template caps bodies at 5 MiB, request header buffers at 4x8 KiB, header/body timeouts at 10/15 seconds. It is a private listener behind reviewed TLS ingress, not a complete public certificate deployment. Provider object timeouts are bounded. Infrastructure must also configure connection/concurrency limits and capacity monitoring.

## Headers, sessions and logging

All API outcomes including early 403/429/413 have request ID, nosniff, no-store, no-referrer, denied framing, restrictive CSP and device permissions. Production adds HSTS. Existing exact-origin mutation/CSRF and narrow credentialed CORS rules remain. No new login or session bypass.

Next.js proxy supplies a fresh random CSP nonce for scripts and strict-dynamic, object-src none, frame-ancestors none and same-origin fetches/fonts. Root layout renders dynamically so the framework can attach matching nonces. Production scripts use neither unsafe-inline nor unsafe-eval. Development retains unsafe-eval for the documented React debugging requirement. Existing React style attributes require style-src unsafe-inline; this is explicitly limited to styles and preserves approved layouts. No external fonts, analytics, new visual scripts or public evidence URLs were added. HSTS is sent by production web/API, intended for HTTPS deployment.

Structured logs contain timestamp, level, event, request ID, templated route, method, status and duration. Unknown paths are 'unmatched'; queries, filenames, payloads, tokens, credentials and exception messages are excluded. Monitoring export failures do not break requests. Disable Uvicorn/proxy query-bearing access logs or use a reviewed redacted format. No signed URLs exist.

## Containers and CI

Existing non-root API Dockerfile is retained. New multi-stage standalone Next.js Dockerfile runs as node. Production compose keeps API/web private, drops capabilities, applies no-new-privileges, and gives the API a read-only root with temporary scratch. Runtime secrets are injected from an external env file; .dockerignore excludes .env*, .runtime, keys, local DB/files and test artifacts. Proxy template binds only loopback until a reviewed HTTPS ingress is installed. Pin deployment image digests during release approval; registry image provenance and actual container execution are separate gates.

CI extends existing tests with a real private S3 gateway, integrity checks and migration roundtrip. Local verification is not a remote CI run. Docker execution, image scanning, ingress/TLS rollout and remote CI are UNVERIFIED unless an observed run is recorded in the Batch 6 report.
