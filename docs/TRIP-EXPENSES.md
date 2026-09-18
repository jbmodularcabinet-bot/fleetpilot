# Trip expenses — Batch 8

Operational PHP cost inputs only. No revenue, profitability, accounting recognition, reimbursement or payroll calculation. Cash advances and allowances are inputs, not assertions of final accounting treatment.

## Domain

`trip_expenses` owns identity, tenant, trip, assigned vehicle/driver snapshot, current revision, source, submitter, review and void state. `expense_revisions` holds immutable financial details. `expense_evidence` holds private receipt metadata and supersession history. SQLAlchemy domain mappings are registered in migration metadata. Commands and aggregates use SQLAlchemy parameterized SQL; financial aggregates execute in PostgreSQL. No client total is accepted. A separate internal vehicles.reviewed_fuel_odometer retains the highest reviewed reading without changing Vehicle.odometer or exposing other drivers' records.

Categories: FUEL, TOLL, PARKING, DRIVER_ALLOWANCE, DRIVER_CASH_ADVANCE, HELPER_ALLOWANCE, LOADING_FEE, UNLOADING_FEE, SUBCONTRACTOR, OTHER. Other requires at least three trimmed explanation characters; subcontractor requires a vendor/payee. Every entry has an explicit occurrence timestamp with timezone, PHP currency and server-recorded submission actor/time. Driver and vehicle derive from the assigned trip; no client ownership fields or cross-trip movement are accepted.

Writes require an assigned, dispatched, nonterminal trip. Scheduled, completed and cancelled trips reject new expense operations. Review/correct/void and receipt uploads must therefore happen before operational closeout. This conservative policy does not change trip lifecycle transitions. Historical reads remain available subject to current authorization.

## Exact money

API decimal values are plain strings: no JSON numbers, exponent, NaN, infinity, sign, separators or excess precision. PostgreSQL NUMERIC and Python Decimal store/compute amounts. Amount >0 and <=10,000,000 PHP, at most two decimal places. Currency is PHP. Server aggregates return decimal strings. The UI formats strings and estimates fuel through BigInt fixed-point arithmetic; it does not calculate authoritative totals using Number.

Submitted total means all current SUBMITTED plus REVIEWED amounts; VOIDED is excluded. Reviewed total means only current REVIEWED amounts. Totals cover the entire authorized trip, not just the displayed page. Corrections replace the current contribution and reset review. Category totals are from current revisions. Vehicle fuel history displays current Fuel records, including explicit void state, and never computes efficiency.

## Authorization and API

Owner/admin/manager/accounting receive expense read/create/review/correct/void, fuel read/create/review and expense evidence read/upload. Dispatcher receives the same except correction/void. Driver has only own read/create; no review/correction/void. Accounting retains its existing navigation permissions; expense capabilities do not imply unrelated dispatch permissions. Restrictive overrides remain supported.

- GET/POST `/api/v1/trips/{trip_id}/expenses`
- GET `/api/v1/expenses/{id}`
- POST `/api/v1/expenses/{id}/{review|correct|void}`
- POST `/api/v1/expenses/{id}/evidence`
- GET `/api/v1/expense-evidence/{id}`
- GET `/api/v1/vehicles/{id}/fuel-history`
- POST `/api/v1/driver/sync/{trip_id}/expense`

Lists use bounded pagination (default 20, maximum 100), deterministic submission-time/ID ordering and tenant-scoped server aggregates. Detail fetches revision and evidence collections in bounded query count; list rendering does not issue one query per item.

Every mutation requires expected Trip.version and a UUID Idempotency-Key. Organization serialization, renewed membership checks and immutable Batch 7 command receipts protect concurrent review/correction/replay. Normal expense commands share that receipt infrastructure; its historical table name `driver_sync_commands` is retained although owner expense operations now use it too. Receipt and operation commit in the same database transaction. Same key/data replays; altered data conflicts. Current access is checked before replay. Expense changes increment Trip.version without creating trip lifecycle milestones.

## Receipts

Optional for every category. JPEG/PNG/WebP only; nonempty <=5 MiB, <=16 million pixels, one frame, matching MIME/extension/decoded format. Existing pixel normalization produces PNG and removes metadata/trailing payloads. At most 12 retained files per expense. Original filenames never select storage paths. Opaque organization/UUID object keys are not public URLs and are omitted from client metadata. Existing local/S3 abstraction, private authorized byte retrieval, checksums, rate limits, transaction compensation and operator reconciliation are reused. Reconciliation/snapshots now include both delivery and expense evidence.

Uploads are separate acknowledged commands following creation. An expense can be accepted while a selected optional receipt remains pending/failed; the UI must not describe that receipt as uploaded. Offline dependencies preserve it for retry. No distributed storage/database transaction is claimed; hard-crash orphan handling remains report-only reconciliation.

## Scope boundaries

No new financial dashboard or bottom navigation. Additions live in existing Trip Detail and vehicle detail cards. Existing owner/driver lifecycle and POD controls remain. Production deployment, physical devices, Safari, load and external assessment remain separate unverified gates unless recorded otherwise in the Batch 8 report.
