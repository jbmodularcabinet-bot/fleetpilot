# Foundation verification

Verified locally on Windows, Node 24.20.0, Python 3.12.14 and PostgreSQL 18.4. Database tests use real PostgreSQL and the restricted runtime role, not mocks or SQLite.

| Check | Result |
| --- | --- |
| Initial development/test migration | Passed |
| Isolated test database downgrade to base and upgrade to head | Passed |
| API unit and PostgreSQL integration suite | 42 passed |
| Web component/helper suite | 4 passed |
| Playwright browser suite using installed Chrome | 8 passed, exit code 0 |
| Strict web/shared-package and E2E TypeScript check | Passed |
| ESLint and Python Ruff | Passed |
| Production Next.js build | Passed; protected pages dynamically rendered |
| API startup, liveness and readiness | Passed |
| Python dependency compatibility | `pip check` passed |

API coverage includes role parsing, deny-only permission overrides, field validation, unknown roles, HTTPS production configuration, session hashing/expiry/logout/tampering, CSRF, login rate limiting, all seven role boundaries, active membership checks, suspended organizations, cross-tenant IDs and forged selection, authorized switching, duplicate membership, self-change/admin escalation rejection, audited updates/disabling, immutable audit records, direct SQL RLS denial, transaction-local context reset, and rollback when an audit write fails.

Browser coverage includes owner login and redirect, dashboard placeholders, organization edits surviving reload, member listing, logout and protected-route redirect; driver login/navigation/profile and direct administration-route denial; mobile widths 360/390/430; desktop widths 1024/1440; bad-password feedback; and a JavaScript-disabled login that cannot submit credentials before hydration. Hydration tests exposed and led to fixes for early native form submission. Login and organization-edit forms are now disabled until hydrated and use explicit POST.

Manual verification: local owner login, settings navigation, synthetic legal-name change, reload/persistence and restoration. Owner and driver screenshots reviewed against the approved direction. Review corrected driver-logo clipping and a desktop menu-spacing defect. Automated screenshots are in ignored `test-results/` after E2E; they are test artifacts, not approved standalone branding assets.

Run commands are in README. Tests may reset only the explicitly named `fleetpilot_test` database. Never point integration tests at development/production. Do not run pytest and E2E simultaneously against the same database. E2E uses ports 8100/3100 and a separate `.next-e2e` build directory. Some Windows sandboxes prevent Playwright from terminating child servers; the verified run used permission to manage those test processes and completed cleanly. Do not report a hung teardown as a successful command.

The production build and local startup are verified; the supplied Docker alternative and GitHub Actions workflow have not run on a Docker host or remote CI service. Full operational golden flows, offline behavior, PWA installation, external monitoring, deployment, production backup recovery and domain isolation tests are outside Batch 2 and remain unverified.
