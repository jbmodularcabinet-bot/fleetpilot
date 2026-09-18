# FLEETPILOT BATCH 11 REPORT

Verification date: 17 September 2026.

BATCH 11 STATUS: CONDITIONAL PASS — all local maintenance and regression gates passed; inherited external/device/production gates remain UNVERIFIED.

DESIGN LOCK: PASS — original assets, design tokens, navigation and shells preserved; desktop/mobile rendered checks passed.

## Audit before implementation

Read Batch 3/4/6/7/8/9/10 reports and the requested trip lifecycle, offline, fuel/expense, adjustment and design documentation. Inspected source models, migrations, actual vehicle statuses, trusted fuel odometer, trip eligibility, permissions/RLS, audit, private storage, queue/idempotency, owner Fleet and Driver UI, test harness and deployment readiness. Source had no maintenance domain to extend. Vehicles supported AVAILABLE/ASSIGNED/INACTIVE; the trip eligibility function rejected only INACTIVE. Existing immutable expenses, private images and offline receipts were reusable and retained.

Batch 10 source/test baseline agrees with its report: 337 cases (269 backend, 36 frontend, 32 browser). No prior test was deleted or skipped. The prompt's 48,900 km UPCOMING example conflicts with its 50,000 due/1,000 warning and later precise examples; this implementation uses the exact inclusive 49,000 warning boundary. Deployment readiness documentation is updated from 0008 to the actual new 0009 head. Prior batch reports remain historical.

## Implemented

| Area | Delivered behavior |
| --- | --- |
| Maintenance schedules | Explicit service types; odometer, date and whichever-first intervals; warnings; active flag; strict create/update APIs and native creation form. |
| Due logic | Server-derived OK/UPCOMING/DUE/OVERDUE; maximum trusted owner/reviewed-fuel/completed-service reading; UTC date semantics. Attention rows carry real status values. |
| Work orders | Tenant-local numbering; preventive/repair/inspection/defect response/other; priority, provider, optional same-vehicle source/trip, versioned explicit lifecycle, terminal history. |
| Downtime and availability | Explicit intervals; downtime only when requested; active-trip start blocker; multiple-maintenance blocker handling; preserve INACTIVE; restore ASSIGNED/AVAILABLE only when valid. |
| Dispatch protection | Existing create/assign/dispatch rejects maintenance or inactive vehicles; DB guards prevent bypass; master unassignment cannot clear downtime. |
| Service completion | Work performed and trusted odometer required; atomic completion, schedule next due, defect resolution, vehicle availability and history/audit. |
| Maintenance cost | Append-only PART/LABOR/OTHER items, Decimal/NUMERIC PHP, server-rounded totals, private image receipts/invoices/before/after photos. |
| Trip-cost separation | Optional trip reference is context only. PHP 5,000 trip expense remains 5,000 beside PHP 12,000 maintenance. |
| Driver defects | Own current fleet vehicle or own nonterminal trip; server-derived driver; severity/category/description; immutable original; owner review/dismiss/create work/resolve. |
| Offline sync | Existing IndexedDB/worker/queue, report + dependent photos, local acknowledgment only after durable save, replay/lost-response recovery, session/account restrictions. |
| Owner UI | Vehicle Maintenance, next service, open work, service history, defect review; native attention/upcoming/open/history list and work detail. |
| Evidence | Existing storage abstraction/validation/normalization/checksum/rollback cleanup; authenticated private retrieval; no public upload paths or silent replacement. |
| Authorization | Explicit maintenance/defect capabilities, restrictive overrides, own-driver boundaries, forced RLS, composite tenant references. |
| Audit | Immutable maintenance events separate from audit; schedule/work/cost/evidence/defect actions include actor, organization and related entity identifiers. |

No maintenance cost is inserted into trip expenses. No profitability, accounting, invoicing, GPS, AI, purchasing or customer portal was added. Batch 9 closed-trip adjustment logic remains separate; closed-maintenance corrections are deferred.

## Migration and architecture

`0009_maintenance` follows `0008_closed_trip_adjustments`. Six explicit SQLAlchemy tables: maintenance_schedules, maintenance_work_orders, maintenance_cost_items, driver_defects, maintenance_evidence, maintenance_events. Each has organization ownership and forced RLS. Lookup indexes focus on tenant/vehicle/status/time and parent evidence/cost/history access; tenant work numbers and defect source uniqueness have constraints. DB triggers protect original/terminal history and dispatch/availability safety.

Vehicles gain MAINTENANCE and a monotonic maintenance odometer floor. Existing durable sync receipts permit nullable trip/driver context because vehicle-only defects and owner maintenance commands have no mandatory trip/driver. Existing actor/tenant/key/hash and immutable receipt semantics remain intact; no parallel offline engine.

Executed isolated test rollback to 0008 and reapply to 0009; development forward to 0009. Both catalogs confirm all six new tables have enabled and forced RLS. No development/production rollback was performed. Rollback removes the new domain tables and maintenance odometer; back up before any real downgrade. Durable receipts are retained, so their new nullable context remains on downgrade to avoid destroying immutable history. It is an application-compatible rollback, not a promise of byte-identical old schema or maintenance data retention after table removal.

## Tests and quality gates

| Gate | Result / local evidence |
| --- | --- |
| Full backend regression | 307 passed, 0 failed/skipped, 590.12 s; .runtime/batch11-backend-full.log |
| Final maintenance backend suite | 39 passed, 0 failed, 39.63 s; .runtime/batch11-maintenance-release.log. Includes one additional restrictive permission test and final attention/audit fixes. |
| Unique backend cases verified | 308 = previous 269 + new 39. Repeated cases are not counted twice. |
| Frontend | 41 passed, 0 failed; .runtime/batch11-frontend-final.log (36 previous + 5 new). |
| Full browser/E2E | 34 passed, 0 failed, no retries, 6.7 min; .runtime/batch11-browser-full.log (32 previous + 2 new). |
| Final focused browser | PASS, 2/2 on final source, including 390px owner overflow check; .runtime/batch11-browser-maintenance-release.log (1.1 min) |
| TypeScript | PASS, production build typecheck and explicit typecheck; final log .runtime/batch11-typecheck-release.log |
| Lint | PASS; final log .runtime/batch11-lint-release.log |
| Python | PASS, Ruff/compileall; .runtime/batch11-python-final.log |
| Dependencies | pip check and npm ls --all --omit=optional passed. No dependency additions or fresh vulnerability-feed audit. |
| Production Next build | PASS; .runtime/batch11-build-release.log; actual standalone output used by browser tests. |
| API startup / health / readiness | LOCAL PASS; real test API process and /health + /ready both 200 in browser golden. No deployment certification. |
| Migration | Forward/rollback/reapply exited successfully; .runtime/batch11-migration-*.log; final revision/RLS catalog .runtime/batch11-schema.json. |
| Design originals | 6/6 SHA-256/size checks passed; .runtime/batch11-assets-final.log. |

Unique automated coverage: 383 cases = 308 backend + 41 frontend + 34 browser, including all previous 337 and 46 new. Final focused backend/browser rechecks passed. Total: 383 passed / 0 failed / 0 skipped. No unexecuted external check is counted as a test pass.

## Golden workflows and security

Preventive golden: TRK-001 trusted 48,000, oil baseline 45,000 and 5,000 interval → 50,000 due; advance 49,100 UPCOMING and 50,100 OVERDUE; start downtime → MAINTENANCE; reject trip assignment/dispatch; add exact 1,234.56 + 500.00 + 100.10 = 1,834.66; attach private image; complete at 50,250 → 55,250 next due; preserve history, audit and valid availability. Reload persistence verified. Backend covers the reading advances; browser covers real owner forms, evidence, completion/list/history and reload.

Defect golden: Juan's assigned vehicle, SERIOUS/BRAKES/“Brake pedal feels softer than normal.” and photo saved offline; close/reopen; reconnect; deliberately drop committed report response; retry same key → ALREADY_APPLIED; exactly one report/photo; owner review creates linked work; start/repair completion resolves report while preserving description/photo/history. Concurrent duplicate report/photo requests also pass at API level.

Tenant isolation: API known UUID/list/search/count/mutation/upload attacks and all six populated PostgreSQL tables deny Tenant B. Cross-driver read/photo/upload/report attempts fail. Role and restrictive-permission denials, malformed/oversized/spoofed files, direct availability tampering, immutable costs/closed work, exact money, trusted odometer, multiple blockers and audit-rollback checks passed. See BATCH-11-SECURITY-REVIEW.md for boundaries and limitations.

## Design and files

Existing logo/wordmark/Inter/palette/nav/shell/CSS/assets retained. New panels reuse existing cards, forms, chips, buttons, loading/error/empty patterns. Desktop, 390px owner and 390px Driver screenshots reviewed; no horizontal overflow. Browser assertion helper accepts a maintenance panel while preserving its POD default and all existing token/nav/card checks. The initial new browser failure was the incorrect POD heading check, not waived application behavior.

20 source/document files created, 21 existing files modified; full list: BATCH-11-FILES.md. Generated worker included; private runtime logs and build caches excluded. Screenshot evidence retained in .runtime/batch11-screenshots/: batch11-maintenance-owner.png, batch11-maintenance-owner-mobile.png and batch11-defect-offline.png. The offline capture intentionally shows the existing failed-network/retry state while the two records remain saved; subsequent replay and sync passed.

## Known limitations, risks and UNVERIFIED items

- PHP only; simple cost lines and provider text; no parts inventory or purchasing.
- Completed maintenance/cost corrections, active-work cancellation, and administrative reopen are deferred. Original lines are never silently rewritten.
- Schedule update/deactivation is API-only; UI creation is implemented. Vehicle overview shows recent 100 work/defect records; list pagination retains access to older records.
- No full scheduling engine. Active-trip downtime is conservatively blocked; scheduled dispatch checks availability at action time.
- Photos sync separately; owner closure before a delayed upload yields Needs attention. Browser local storage may be evicted. No physical force-kill guarantee.
- Current maintenance workflow verification uses local private filesystem storage; existing S3 adapter is reused. Maintenance evidence is included in backup/reconciliation enumeration, but no new maintenance-specific remote restore drill was executed.
- Physical Android, actual Safari/iOS, Docker execution, remote CI, staging/production deployment, remote object storage/IAM, external monitoring, remote backup/restore, deployed tenant/cross-driver attacks and independent security assessment: UNVERIFIED.
- Maintenance-specific load testing and production operation: UNVERIFIED. Existing earlier-batch local results do not certify the new feature in production.
- Vite emits an existing future config-loader warning; configured tests pass. No unrelated dependency upgrade undertaken.

Recommended Batch 12 scope: finish accessible device/staging/private-storage and operational recovery verification before expanding feature scope; consider a separately specified append-only closed-maintenance correction workflow if required. Nothing in Batch 12 is started.

## Domain documentation

- MAINTENANCE-SCHEDULES.md
- MAINTENANCE-WORK-ORDERS.md
- DRIVER-DEFECT-REPORTING.md
- VEHICLE-DOWNTIME.md
- MAINTENANCE-COSTS.md
- BATCH-11-SECURITY-REVIEW.md
- BATCH-11-DESIGN-VERIFICATION.md
- BATCH-11-FILES.md
