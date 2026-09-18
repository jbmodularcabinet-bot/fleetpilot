# FleetPilot

**Run the fleet. Not the chaos.**

Batch 5 proof of delivery and delivery exceptions: private photos/signatures, recipient confirmation, preserved delivery attempts, operator review and on-site retry, built on the existing fleet master data, dispatch, authentication, RBAC, forced RLS and audit infrastructure. See [Batch 5 verification](docs/BATCH-5-REPORT.md) and [delivery evidence rules](docs/DELIVERY-EVIDENCE.md).

## Local setup

Requires Node 22+ (verified with 24.20.0) and Python 3.12. Commands below run at the repository root. On Windows use `npm.cmd` if PowerShell blocks `npm.ps1`; replace `.venv/bin/python` with `.venv/Scripts/python.exe`.

```sh
npm ci
python -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements.txt
npm run db:local
```

Keep the database terminal running. It starts a real PostgreSQL 18 cluster bound to loopback, generates local random credentials, and creates separate development/test databases. It writes `.env` only if absent and stores local credentials under the ignored `.runtime/` directory. No global database service is installed. An existing `.env` is preserved; ensure it points to this cluster before continuing. Run local services as a normal user, not root.

In another terminal:

```sh
.venv/bin/python scripts/api-task.py alembic upgrade head
.venv/bin/python scripts/api-task.py fleetpilot.seed
.venv/bin/python scripts/api-task.py uvicorn fleetpilot.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In a third terminal:

```sh
npm run dev
```

Open [FleetPilot](http://localhost:3000). Use exactly `localhost` in the browser; mutation origins must match `WEB_ORIGIN`.

Synthetic accounts: `carlo@example.com` (Owner), `juan@example.com` (Driver), and `other-owner@example.com` (separate isolation organization). Their generated password is the `DEMO_PASSWORD` value in your local `.env`. Do not share or commit that file. No credentials are embedded in the UI or repository. Seeds are explicit, idempotent, and rejected in production.

The reference implementation uses npm's `embedded-postgres` runtime to make real database testing possible without Docker. Alternatively, configure `POSTGRES_PASSWORD` and `APP_DATABASE_PASSWORD` and run `docker compose --env-file .env -f infrastructure/compose.yaml up -d`. Follow `.env.example` to set both connection URLs. Do not run both database alternatives on the same port. Docker configuration is supplied but requires separate verification on a Docker host.

## Checks

```sh
npm run typecheck
npm run lint
npm test
.venv/bin/python -m ruff check apps/api scripts
.venv/bin/python scripts/api-task.py --test alembic upgrade head
.venv/bin/python scripts/api-task.py --test pytest -q
.venv/bin/python scripts/api-task.py --test fleetpilot.seed
npx playwright install chromium
npm run test:e2e
```

For installed Chrome, set `PLAYWRIGHT_CHANNEL=chrome` instead of downloading Chromium. E2E starts isolated API/web services on 8100/3100 and uses `fleetpilot_test`; do not run API integration tests at the same time. Test-only data is reset by the integration suite. Browser output and traces are ignored and may contain synthetic test data.

Production build: explicitly set `API_INTERNAL_URL` and run `npm run build`. To serve it, run `npm run start --workspace @fleetpilot/web`. API production requires `ENVIRONMENT=production` and HTTPS `WEB_ORIGIN`; terminate TLS at a trusted proxy and expose only the web origin. The API refuses superuser/BYPASSRLS runtime database connections. See [security](docs/SECURITY.md) before deployment.

## Structure

```text
apps/web/             Next.js App Router, owner and driver shells
apps/api/             FastAPI, domain-independent foundation, Alembic, pytest
packages/ui/          Shared shell components and design tokens
packages/types/       Web API DTO types
packages/auth/        Client display permission helpers
packages/config/      Strict TypeScript baseline
infrastructure/       PostgreSQL container alternative and API image
scripts/              Local database and environment-specific task runner
tests/e2e/            Browser golden flows and responsive checks
docs/                 Architecture, security, API, verification and ADRs
```

Provision accounts from an operator terminal with `python scripts/api-task.py fleetpilot.provision --email person@example.com --name "Person Name"`. It prompts for an initial password without echoing it. Optionally add `--organization "Business Name" --slug business-name` to create an organization and its owner atomically. Existing passwords are never reset by this command. Authorized owners/admins can add provisioned accounts to their organization in Settings. Public signup, email invitations, password recovery, MFA, and phone OTP are not exposed in Batch 2.

Phase 0 is preserved in [the audit](docs/PHASE-0-REPOSITORY-AUDIT.md). Historical [Batch 2 verification](docs/BATCH-2-REPORT.md) remains unchanged. See the [Batch 3 report](docs/BATCH-3-REPORT.md), [security review](docs/BATCH-3-SECURITY-REVIEW.md), and [file inventory](docs/BATCH-3-FILES.md).

## Fleet master data

Owners/admins/managers can manage Customers, Fleet → Vehicles and Fleet → Drivers. Dispatchers have read access to master data; accounting reads customers; maintenance reads vehicles. Driver accounts see their own linked profile, current vehicle and assigned trips. Per-membership restrictive overrides still apply.

Create a customer, a vehicle and a driver profile; open either vehicle or driver details to assign them. One driver and one vehicle may each have at most one current assignment. Unassign explicitly before replacement or deactivation. History is retained. A driver login is optional; only users with `users.manage` may link an existing active driver account in the same organization.

APIs: `/api/v1/customers`, `/vehicles`, `/drivers` expose list, create, get, PATCH update and POST `/{id}/deactivate` / `/{id}/reactivate`. PATCH accepts the complete editable profile defined by the OpenAPI input schema; omitted optional profile values become null/default. Status and tenant/actor IDs cannot be set through profile bodies. Lists support `search`, `status`, allowlisted `sort`, `direction`, `limit` and `offset`, returning `{items,total,limit,offset}`. Status changes are explicit actions; hard deletion is unavailable.

`/api/v1/vehicle-driver-assignments` exposes create/list/get and POST `/{id}/unassign`. List filters include `vehicle_id`, `driver_id`, `is_current`, `search`, `sort`, `direction`, `limit`, `offset`. `/api/v1/driver-profile` returns only the authenticated driver's linked profile and current vehicle. Audit filters accept `entity_type` and `entity_id`; vehicle/driver histories include their assignment events.

Migration `0002_fleet_master` creates the four domain tables, constraints, indexes, forced RLS and assignment-history trigger. Apply with the existing `alembic upgrade head` command. Rollback drops Batch 3 data; the verified rollback/reapply procedure uses only `fleetpilot_test`. Back up production data before any operator-directed downgrade.

## Dispatch and trips

Owner/admin/manager/dispatcher roles can use Operations → Dispatch Board. Create a scheduled trip with an existing active customer, pickup/delivery details and schedule; assign one active vehicle and driver together. Dispatch and follow the permitted next action. Delivery confirmation and operator-reviewed completion are separate. Cancellation requires a reason and is available only before delivery. Completed/cancelled trips are read-only. Operator notes have a separate update action. Trip assignments never overwrite fleet-master assignments.

Drivers need a linked active driver profile to see their own assigned trips. They can record pickup/loading/delivery milestones after an operator dispatches the trip. They cannot dispatch, cancel, complete, reassign or enumerate tenant-wide trips. GPS, maps tracking, offline sync, fuel, expenses and financial features remain outside this batch.

`/api/v1/trips` supports create/list; `/{id}` supports read and full-profile PATCH while scheduled. Dedicated actions: POST `/{id}/assign`, `/transition`, `/cancel`, `/complete`; PATCH `/{id}/notes`; GET `/{id}/milestones` and `/assignments`. Every existing-trip mutation requires `expected_version`. Transition bodies accept an allowlisted `action`, never an arbitrary status. `/api/v1/dispatch` provides the board list. Lists support `view`, `search`, `status`, `customer_id`, `vehicle_id`, `driver_id`, `date_from`, `date_to`, allowlisted `sort`, `direction`, `limit`, `offset`. Driver endpoints are `/api/v1/driver/trips`, `/{id}`, `/{id}/milestones`, and POST `/{id}/transition` with own-trip enforcement.

Migration `0003_dispatch_trip_lifecycle` adds trips, trip milestones and operational assignment history with forced RLS, composite tenant references, active-resource uniqueness and immutable-history/closed-trip guards. Apply with `alembic upgrade head`. Downgrade deletes Batch 4 data and is tested only in the isolated test database. [Lifecycle documentation](docs/TRIP-LIFECYCLE.md) specifies action mapping, the 24-hour fallback reservation window, version conflicts, terminal states and timezone behavior. [Security review](docs/BATCH-4-SECURITY-REVIEW.md) and [file inventory](docs/BATCH-4-FILES.md) describe implementation boundaries.

## Proof of delivery and exceptions

Apply migration `0004_proof_of_delivery` with the existing upgrade command. At the delivery stop, a driver can report an issue or, after unloading, submit recipient details, at least one delivery photo, optional confirmed signature and notes. Successful POD marks DELIVERED. An operator reviews POD before completing the trip. A failed attempt retains evidence and blocks further progress until the operator explicitly authorizes an on-site retry. A retry creates another numbered attempt; it never overwrites the first.

Uploads accept JPEG/PNG/WebP, up to 5 MiB and 16 megapixels, with 12 retained files per attempt. Files are decoded and normalized; originals with embedded metadata are not retained. Private development/test objects live under ignored `.runtime/evidence-development` / `.runtime/evidence-test`, outside public assets. Optional `EVIDENCE_STORAGE_ROOT` selects a private operator-controlled directory. Evidence retrieval always uses authenticated `/api/v1/evidence/{id}` and enforces tenant and driver ownership.

**Production object storage is NOT CONFIGURED / UNVERIFIED.** Production evidence operations return 503 until a verified adapter is supplied. Back up the database and private object directory together; no ordinary evidence deletion, automatic retention cleanup or offline upload queue exists. [Delivery evidence contract](docs/DELIVERY-EVIDENCE.md) documents policy, endpoints, legacy trips, storage limits and transaction boundaries. [Batch 5 security review](docs/BATCH-5-SECURITY-REVIEW.md) records the implemented controls and remaining production risks.
