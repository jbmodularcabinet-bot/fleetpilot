# Batch 15 resumed security review — 19 September 2026

Scope: existing legacy completed-trip expense acceptance, financial snapshots, API/RLS boundaries, and local recovery. This is an engineering review, not independent security certification.

## Findings and fixes

- **Response before durable commit:** a direct installed-FastAPI probe produced open → response → commit. Request-scoped cleanup allowed success before commit for routes lacking an explicit commit, exposing a just-created trip as temporarily absent. All shared database dependencies now use function scope; authentication service factories return objects rather than unnecessarily yielding. Database/session/auth architecture and existing explicit atomic commits remain intact. Regression tests assert commit precedes HTTP 200 and failed commit rolls back before HTTP 500; a structural guard prevents request-scoped database dependencies from returning.

- **Stale financial review token:** migration 0012 did not invoke financial invalidation when a legacy expense was accepted. A reviewer could approve with a token from before that cost entered the reviewed total. Migration 0013 attaches the existing immutable invalidation trigger; acceptance changes the token atomically. A stale-token regression requires rejection before fresh approval.
- **Database role boundary:** the legacy SELECT policy checked active membership and deny overrides but omitted allowed roles. Direct runtime-role SQL could expose same-tenant acceptance metadata to driver/dispatcher/maintenance roles. Migration 0013 restricts reads to OWNER, ADMIN, MANAGER and ACCOUNTING, matching financial-read capabilities. Direct PostgreSQL tests populate acceptance history before testing denial.
- **Restrictive permissions:** legacy fuel acceptance omitted fuel.review, and the database guard omitted financial-review/expense read overrides. API and database now enforce those restrictions. The new database guard obtains the existing organization lock before eligibility checks.
- **Duplicate command:** another idempotency key for an accepted expense previously reached a unique-constraint failure. It now returns explicit HTTP 409; replay with the original key remains ALREADY_APPLIED. Database uniqueness remains the race backstop.

Original expense revisions/status, lifecycle/POD, ownership and audit history are unchanged. No public file route, new secret, SQL interpolation of user input, or arbitrary mutation endpoint was introduced. The migration is additive to the already committed 0012; historical migration source is not rewritten.

## Verification

39 targeted legacy/governance cases passed, including seven new regression cases. Tests cover same-tenant denied roles, restrictive fuel/expense/read overrides at API and direct SQL, immutable history, tenant boundaries, source preservation, stale approvals, duplicate acceptance and replay. Three additional transaction-ordering cases were added after browser regression exposed the lifecycle gap. Full release results are recorded in BATCH-15-RESUMPTION.md.

The local recovery drill restored acceptance/review/audit/settlement records and hash-verified private evidence across 32 forced-RLS tables. Restored sessions were invalidated. Local self-signed HTTPS and loopback S3 do not establish deployed TLS, production IAM or remote recovery.

## Residual limitations

Owner/admin acceptance is a permanent review overlay, not a reversal or source edit. Corrections/voids use existing administrative adjustments. Accepted SUBMITTED expenses are included in profitability but remain ineligible for ordinary cash-advance expense application, which still requires REVIEWED source status; this pass does not silently broaden settlement policy. No vehicle odometer is propagated by legacy acceptance. Per-advance history remains unpaginated.

Existing remote CI is green only for committed baseline 912f37a, not these uncommitted fixes. Required foundation checks exist on main but enforce_admins is false. Physical Android, actual Safari/iOS, public staging, remote private storage/IAM, external monitoring, remote recovery, deployed isolation and independent assessment remain unverified. No production release is claimed.

## Final executed result

381 backend and 38 production-browser cases passed on the final source; 54 frontend cases passed with unchanged product frontend. The original owner golden now passes without changing its cross-tenant count assertion. No unresolved local blocker remains in this reviewed scope. Overall release remains CONDITIONAL PASS because external gates are unverified.
