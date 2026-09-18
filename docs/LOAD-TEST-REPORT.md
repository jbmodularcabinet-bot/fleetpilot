# Batch 9 controlled load test

LOCAL VERIFIED — disposable restored PostgreSQL, local HTTPS API and private loopback S3. Not production capacity certification.

Concurrency: 4. Total requests: 120. Errors: 0 (0%). Aggregate p50: 186.29 ms; p95: 737.09 ms.

| Route | Requests | p50 ms | p95 ms | Errors |
| --- | ---: | ---: | ---: | ---: |
| Login | 20 | 374.69 | 1830.27 | 0 |
| Trip list | 20 | 198.28 | 640.96 | 0 |
| Dispatch list | 20 | 119.23 | 367.03 | 0 |
| Trip detail | 20 | 83.39 | 304.15 | 0 |
| Expense summary | 20 | 136.01 | 469.82 | 0 |
| Vehicle fuel history | 20 | 187.15 | 515.97 | 0 |

Nearest-rank percentiles from end-to-end HTTP wall time. Four independent authenticated clients, five rounds each; password hashing included in login. No expense/lifecycle mutations during load. Tiny synthetic dataset, single local API process and development host running other verification tasks: results cannot establish fleet-scale performance or an SLO. No bottleneck was demonstrated sufficiently to justify architecture changes.

Evidence: `.runtime/batch9-drill-fdc22679a3b7/load-result.json`. Executable safety guard requires the Batch 9 disposable restore database and loopback URL. No production load was attempted.
