# Test Matrix

| Area | Unit | Integration | UI/E2E | Status |
|---|---|---|---|---|
| App shell | covered | covered | 3 passed | PASS — Batch 1 |
| Domain/SQLite | covered | covered + persistence/migration | n/a | PASS — Batch 2 |
| Brand Brain | 1 validation/domain | 3 CRUD/persistence/migration | 3 Brand Brain UI | PASS — Batch 3 |
| Creative Director | 4 unit/provider | 3 persistence/version/migration | 2 Director UI | PASS — Batch 4 |
| Storyboard | covered | covered + persistence/migration | 2 Storyboard UI | PASS — Batch 5 |
| Asset / generation pipeline | 3 targeted | covered + retry/provenance/migration | regression only | PASS — Batch 6 |
| Provider router/queue | pending | pending | pending | Batch 7 |
| Cost optimizer | pending | pending | pending | Batch 8 |
| Voice/FFmpeg | pending | pending | pending | Batch 9 |
| QA engine | pending | pending | pending | Batch 10 |
| FleetPilot golden path | n/a | pending | pending | Batch 11 |
| SmartRoom/JB regression | n/a | pending | pending | Batch 12 |
| Windows package | n/a | pending | pending | Batch 13 |
| Release candidate | cumulative | cumulative | cumulative | Batch 14 |

Current cumulative verification: 25 backend tests + 10 frontend/UI tests, all passing.
Batch 6 verifies structured asset requirements, deterministic MOCK generation, immutable provenance, idempotent success handling, failure diagnostics, retry chaining, human review states, migration v4↔v5, and full Batch 0–5 regression.
