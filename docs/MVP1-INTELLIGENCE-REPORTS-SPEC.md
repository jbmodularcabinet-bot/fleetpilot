# FleetPilot MVP1 — Intelligence & Reports

Batch 16. Scope authorized in the user's controlled engineering command. The discovered register ended at Batch 15; no existing Batch 16 was overwritten.

## Product surfaces

Owner Dashboard displays reviewed operational revenue, reviewed direct trip cost, contribution, weighted contribution margin, negative-contribution trips and trips requiring financial attention. The owner brief, financial exceptions, category breakdown, customer contribution and material-source-change history use the same backend report result.

Intelligence is deterministic and explainable, with no external AI API. Each finding carries a stable rule/entity/event key, priority, supporting values, comparison basis, qualification, source link and recommended review action. A finding never approves, settles, voids, corrects or finalizes a financial record.

Six report routes provide distinct views:

| Route | Content |
|---|---|
| executive-contribution | Portfolio totals, review confidence, lifecycle subtotals and advance attention |
| trip-contribution | Current effective reviewed trip values, category costs and input/review warnings |
| customer-contribution | Tenant-ID grouping, weighted margin, negative trips and provisional exposure |
| direct-costs | Reviewed versus submitted categories, concentration and excluded funding |
| financial-exceptions | Prioritized findings, supporting values, blockers and source events |
| cash-advances | Separate captured records, confirmed issuance, applications, returns and outstanding balances |

Authenticated CSV and print-ready HTML exports cover the complete filtered report subject to explicit limits. Browser Print / Save as PDF is supported; no automated PDF-generation service is claimed.

## Shared contract

Implementation: reporting_contract.py, reporting_service.py, reporting_rules.py, reporting_exports.py and reporting_routes.py under apps/api/fleetpilot. Existing profitability.calculate_many is authoritative for per-trip figures and finalization. React components render canonical strings and do not calculate business totals.

The report cohort uses scheduled pickup in the organization's IANA timezone: inclusive first-day local midnight and exclusive midnight after the last selected day. Values are current effective values, not historical accounting balances. Lifecycle defaults include cancelled trips; financial status and customer/vehicle/trip filters are explicit. Summaries aggregate all matching trips before page slicing.

Each response identifies organization, scope, timezone, record count, calculation time, rule version, qualifications, warnings and result fingerprint. Re-export is a new calculation, not a promise that an old screen snapshot is retained.

## Demo isolation

The four retained validation records are identified by their actual UUIDs and original synthetic reference labels. Dates remain September 21–24, 2026. The local launcher validates the records read-only, then supplies a tenant-to-trip-ID manifest in process configuration. No seed, date shift, approval or financial-record change is performed. Business reporting excludes configured synthetic IDs. Production rejects local synthetic-manifest configuration and synthetic report requests.

The web app displays SYNTHETIC VALIDATION DATA and explicitly explains that future-scheduled examples are not completed deliveries today. The local demo uses the existing account and development database; it is not a production tenant migration.

## Preservation and runtime

Authoritative development: /home/user/projects/fleetpilot. Branch: feature/mvp1-intelligence-reports. Windows source remains frozen at C:\Users\User\Documents\ChatGPT\FleetPilot. Original uncommitted Batch 15 changes and unrelated capture files are preserved.

The client demo uses WSL-authored source, a WSL-built standalone web artifact and existing Windows platform dependencies/runtime. This is a documented hybrid local runtime, not a completed Linux-native API cutover. The original localhost:3000 application and localhost:8000 API were not replaced. New demo web port: 3500; new API port: 8016 on the explicitly selected private host interface. An authenticated temporary HTTPS tunnel points to the new web server.

## Bounded resources and outstanding scale gate

Limits: 5,000 cohort trips before financial-status filtering, 20,000 rows per bounded funding/history query, 20,000 exported report rows, 10 MB rendered export. Exceeding a limit returns an explicit error; there is no silent truncation. Page size is 1–100. The report calculation deadline is 15 seconds, with 2-second lock and 8-second statement limits.

The 121-trip integration case verifies complete aggregation and a query budget of at most 25 client-visible SQL statements including context/authorization. The requested 1,000-trip/10,000-expense benchmark remains a separate release gate until measured. No production capacity, fleet-wide fuel efficiency, theft detection, net-profit accounting, collections, GPS or general ledger is claimed.

A proposed public-demo responsiveness budget is p95 <= 2.5 seconds across 20 authenticated four-trip requests at concurrency two. This is an acceptance budget, not a measured result; measured results must be attached separately.
