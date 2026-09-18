# Batch 12 recovery verification

17 September 2026. **LOCAL VERIFIED. Remote backup/restore: UNVERIFIED.**

Executed the real loopback HTTPS/private S3-compatible recovery drill using fresh randomly named source and restore databases and buckets. No existing database/bucket was overwritten. The fixture migrated a fresh database to 0009, created synthetic data through authenticated APIs, verified it, restarted the API and reverified it, stopped writers, took a PostgreSQL custom dump and evidence snapshot, restored to another database and private bucket, reconciled objects and verified the restored API. Restored sessions were invalidated before fresh login. Health/readiness returned 200 in each workflow phase.

Evidence: `.runtime/batch12-recovery.log`, `.runtime/batch12-drill-4a24c4c3ed97/result.json`, `drill.log`, `load-result.json`, database dump and object snapshot. Runtime artifacts contain private synthetic data and remain ignored. Restrict access and apply operational retention; no public download links were created.

## Results

- Trip completed; customer/vehicle/driver, immutable milestones and reviewed POD persisted.
- Fuel PHP 3,000, toll PHP 300, parking PHP 100 and immutable +50 closed adjustment yielded PHP 3,450. Original toll remained PHP 300.
- Serious brake defect retained original notes; schedule, resolved defect, work order and downtime history persisted. Service completion at 50,250 km produced next due 55,250 km.
- Maintenance parts/labor totaled PHP 12,000 and did not enter the trip expense total. Vehicle returned ASSIGNED because its master assignment remained current.
- Five authorized image downloads matched their recorded SHA-256 checksums: POD photo, signature, expense receipt, defect photo and maintenance receipt. Missing/corrupt/orphan reconciliation found no discrepancy.
- Anonymous and foreign-tenant evidence access was denied; the assigned driver could read the original defect/photo but could not manage owner work orders. The restored defect command replayed ALREADY_APPLIED with the same ID.
- Restored row counts matched the source snapshot; all 26 restored RLS tables were enabled and forced. Local API ownership tests and the complete backend adversarial suite complement this catalog check; deployed isolation remains UNVERIFIED.
- Local production-mode authentication cookies included Secure, HttpOnly and SameSite=Lax; API responses included CSP/frame-ancestors, HSTS, nosniff, referrer and permissions headers. A self-signed test certificate is not public TLS certification.

The exact proposed physical workflow was not run: no Android/staging target exists, and starting downtime during an active trip conflicts with the verified safety blocker. This local fixture closes the trip first. Offline capture/replay is independently covered by desktop browser tests, not claimed as a physical recovery golden.

## Source/restored row counts

| Table | Matching count |
| --- | ---: |
| users | 3 |
| organizations | 2 |
| trips | 1 |
| trip_milestones | 14 |
| audit_logs | 49 |
| delivery_attempts | 1 |
| proof_of_delivery | 1 |
| delivery_evidence | 2 |
| trip_expenses | 3 |
| expense_revisions | 3 |
| expense_evidence | 1 |
| closed_trip_adjustments | 1 |
| expense_effective_values | 1 |
| customers | 1 |
| vehicles | 1 |
| drivers | 1 |
| maintenance_schedules | 1 |
| maintenance_work_orders | 1 |
| maintenance_cost_items | 2 |
| driver_defects | 1 |
| maintenance_evidence | 2 |
| maintenance_events | 13 |
| driver_sync_commands | 13 |

## Supplementary LOCAL load test

Concurrent with backend regression on the same workstation, so timings include shared-host load. Five workers, 12 iterations each, nine routes: 540 requests. No production target was exercised. This bounded synthetic sample is not a capacity certification and does not justify architectural optimization.

Overall p50 120.03 ms; p95 420.51 ms; p99 703.39 ms; errors 0; timeouts 0.

| Route | Requests | p50 ms | p95 ms | p99 ms | Errors | Timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| login | 60 | 297.2 | 952.42 | 1110.87 | 0 | 0 |
| /trips | 60 | 168.05 | 351.3 | 477.82 | 0 | 0 |
| /dispatch | 60 | 112.65 | 281.33 | 418.36 | 0 | 0 |
| /trips/{id} | 60 | 93.9 | 397.56 | 492.35 | 0 | 0 |
| /trips/{id}/expenses | 60 | 118.96 | 377.26 | 449.12 | 0 | 0 |
| /vehicles/{id}/fuel-history | 60 | 123.09 | 288.72 | 748.47 | 0 | 0 |
| /maintenance/work-orders | 60 | 68.0 | 256.1 | 418.93 | 0 | 0 |
| /vehicles/{id} | 60 | 63.22 | 299.61 | 560.83 | 0 | 0 |
| /maintenance-evidence/{id} | 60 | 121.63 | 391.09 | 563.37 | 0 | 0 |

Remote object storage, remote durability/IAM, external monitoring, remote RPO/RTO, deployed isolation and staging load remain UNVERIFIED.
