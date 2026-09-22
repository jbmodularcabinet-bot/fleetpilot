# Test Matrix

| Area | Unit | Integration | UI/E2E | Status |
|---|---|---|---|---|
| App shell | covered | covered | 3 passed | PASS — Batch 1 |
| Domain/SQLite | covered | covered + persistence/migration | n/a | PASS — Batch 2 |
| Brand Brain | 1 validation/domain | 3 CRUD/persistence/migration | 3 Brand Brain UI | PASS — Batch 3 |
| Creative Director | 4 unit/provider | 3 persistence/version/migration | 2 Director UI | PASS — Batch 4 |
| Storyboard | covered | covered + persistence/migration | 2 Storyboard UI | PASS — Batch 5 |
| Asset / generation pipeline | 3 targeted | retry/provenance/migration | regression only | PASS — Batch 6 |
| Provider router/queue | 7 targeted | routing + queue + recovery + migration | regression only | PASS — Batch 7 |
| Cost optimizer | 13 targeted | currency + FX + budget + persistence + migration | regression only | PASS — Batch 8 |
| Voice/FFmpeg | 7 targeted | voice + timeline + render + ffprobe + rollback | real preview proof | PASS — Batch 9 |
| QA engine | pending | pending | pending | Batch 10 |
| FleetPilot golden path | n/a | pending | pending | Batch 11 |
| SmartRoom/JB regression | n/a | pending | pending | Batch 12 |
| Windows package | n/a | pending | pending | Batch 13 |
| Release candidate | cumulative | cumulative | cumulative | Batch 14 |

Current cumulative verification: 52 backend tests + 10 frontend/UI tests, all passing.
Batch 9 verifies deterministic MOCK voice, restart persistence, failure evidence, ordered timelines, safe FFmpeg argument building, path/dimension/duration bounds, real ffprobe-verified preview rendering, render idempotency, source checksum protection, retained render-attempt evidence, and migration v7↔v8.
