# Test Matrix

| Area | Unit | Integration | UI/E2E | Status |
|---|---|---|---|---|
| App shell | covered | covered | 3 passed | PASS — Batch 1 |
| Domain/SQLite | covered | persistence/migration | n/a | PASS — Batch 2 |
| Brand Brain | covered | CRUD/persistence/migration | 3 Brand Brain UI | PASS — Batch 3 |
| Creative Director | covered | persistence/version/migration | 2 Director UI | PASS — Batch 4 |
| Storyboard | covered | persistence/migration | 2 Storyboard UI | PASS — Batch 5 |
| Asset / generation pipeline | covered | retry/provenance/migration | regression only | PASS — Batch 6 |
| Provider router/queue | covered | routing + queue + recovery | regression only | PASS — Batch 7 |
| Cost optimizer | covered | currency + FX + budget + persistence | regression only | PASS — Batch 8 |
| Voice/FFmpeg | 7 targeted | voice + timeline + render + ffprobe | proof render | PASS — Batch 9 |
| Deterministic QA | 23 targeted | lifecycle + idempotency + manifest + rollback | backend-only | PASS — Batch 10 |
| FleetPilot golden path | n/a | deterministic portable fixture | real FFmpeg + QA | PASS |
| Multi-brand foundation | 24 isolation/foundation tests | scoped generation to export | existing UI regression | PASS |
| SmartRoom/JB regression | n/a | pending | pending | Batch 12 |
| Windows package | n/a | pending | pending | Batch 13 |
| Release candidate | cumulative | cumulative | cumulative | Batch 14 |

Current cumulative verification (2026-09-30): 108 backend tests + 10 frontend/UI tests, all passing. Frontend lint and production build pass. Multi-brand proof uses a local test provider, real FFmpeg rendering, all 11 QA checks, human review, and export.
Batch 10 verifies v8↔v9 rollback/reapply, protected Batch 0–9 evidence preservation, concurrent create idempotency, retry lineage, lifecycle terminality, manifest integrity, atomic finalization, critical negative fixtures, proof-render PASS, human review independence, restart persistence, and no render-side effects.
