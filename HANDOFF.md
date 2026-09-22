# Engineering Handoff

## Batch 4 — PASS
Implemented the Creative Director engine and upgraded Director UI.

Added backend:
- `director.py` with CampaignBrief, validation, output validation, provider protocol, deterministic MOCK provider, LIVE adapter stub, and cost estimation
- `director_service.py` with plan generation, approval, versioning, restart persistence, and storyboard materialization
- migration v3 with `director_plans`
- cumulative Director tests

Added frontend:
- structured Director brief fields
- MOCK mode badge
- Strategy / Script / Visual Plan / Asset Needs / Budget tabs
- Generate / Regenerate Strategy
- Approve Plan
- Send to Storyboard
- local proposal version preservation for UI draft workflow

Verification:
- Backend: 18 passed, 0 failed
- Frontend/UI: 8 passed, 0 failed
- Lint: PASS, 0 warnings/errors
- TypeScript: PASS
- Production build: PASS
- Migration v2→v3 / rollback / reapply: PASS
- Approved Director plan restart persistence: PASS
- Regeneration preserves approved prior version: PASS

Regression:
- Batches 0–3 preserved: YES
- Approved CreativeOS UI preserved: YES
- Immutable UI compositing-only rule preserved: YES
- FleetPilot behavior remains fixture/mock data-driven: YES

Known limitations:
- FFmpeg not yet on PATH
- live AI credentials not configured; LIVE adapter intentionally refuses to fake success
- Git author identity not configured
- React UI still uses localStorage for editable proposal drafts until Tauri bridge work; SQLite is authoritative backend persistence

Next permitted batch: Batch 5 — Storyboard production workflow.


## Batch 7 — PASS

Implemented provider-neutral routing and the persistent local generation queue.

Added:
- migration v6 with generation_queue, scheduling/lease indexes, and one-output-per-job uniqueness
- router.py with MOCK capability routing and disabled live provider registrations
- queue.py with atomic claims, claim tokens, leases, same-job retry limits, cancellation, stale recovery, and bounded worker execution
- Batch 7 targeted tests covering migration rollback, routing, atomic claim, restart recovery, retry limits, cancellation-after-return, and idempotent success

Verification:
- Targeted Batch 7: 7 passed, 0 failed
- Full backend: 32 passed, 0 failed
- Frontend/UI: 10 passed, 0 failed
- Lint: PASS
- TypeScript / production build: PASS
- v5→v6→v5→v6 migration path: PASS

Live providers remain disabled unless explicitly configured.
Next permitted batch: Batch 8 — Cost Optimizer.


## Batch 8 — PASS

Added deterministic pre-generation cost intelligence without changing queue execution authority.

Data model:
- campaign budget currency/minor exponent + near-limit bps
- provider_cost_profiles
- fx_snapshots
- cost_recommendations
- cost_estimates
- cost_overrides

Rules:
- integer minor-unit money only
- explicit ISO currency and minor exponents
- Decimal FX with ROUND_HALF_UP
- missing budget/pricing/FX => UNKNOWN
- zero cost requires explicit zero profile
- enabled/capability-compatible/exact-quality routes only
- budget may be overridden with evidence; technical/safety restrictions may not
- historical financial evidence is immutable/versioned

Verification:
- targeted Batch 8: 13/13 PASS
- full backend: 45/45 PASS
- frontend/UI: 10/10 PASS
- lint/build: PASS
- v6→v7→v6→v7 migration path: PASS

Next permitted batch: Batch 9 — Voice/FFmpeg.


## Batch 9 — PASS

Implemented the bounded local voice + FFmpeg composition foundation.

Environment:
- Installed Gyan.FFmpeg 9.0.2 through existing winget.
- Verified absolute ffmpeg/ffprobe binaries and bounded smoke command.
- winget updated user PATH; current RDC process used absolute paths until shell restart.

Backend:
- schema v8: voice_jobs, composition_timelines, composition_timeline_entries, render_jobs, render_attempts
- deterministic MOCK PCM WAV voice adapter
- persistent voice provenance and failure evidence
- ordered restart-safe timeline persistence
- safe structured FFmpeg argument builder using shell=False
- bounded source/output path validation and preview limits
- SHA-256 source/output protection
- ffprobe metadata verification with 0.20s duration tolerance
- deterministic render identity and successful-render reuse
- separate render-attempt evidence for failed/retried execution

Proof:
- 2.000s 640x360 local MP4 with video + audio
- FFmpeg exit 0 / ffprobe PASS
- hero source checksum unchanged
- output SHA-256: 1d8475371b80ee9fdebfb83839128c113d9af48f53ec65a877555b02b04ee9a9
- persistent proof: backend/generated/batch9-proof/proof.sqlite3
- summary: backend/generated/batch9-proof/proof_summary.json

Verification:
- targeted Batch 9: 7/7 PASS
- full backend: 52/52 PASS
- frontend/UI: 10/10 PASS
- lint: PASS
- TypeScript / production build: PASS
- v7→v8→v7→v8 migration path: PASS
- Batch 0–8 regression: PASS

Next permitted batch: Batch 10 — QA Engine.


## Batch 10 — PASS

Implemented deterministic QA over existing verified renders without changing render authority.

Persistence:
- schema v9
- qa_runs
- qa_check_results
- qa_reviews

Rules:
- base identity hashes render job/id/checksum + manifest/rule versions
- canonical attempt 1 reused on repeated/concurrent create
- explicit ERROR retry creates one immutable successor attempt
- lifecycle: PENDING → RUNNING → FINALIZED or ERROR
- artifact defects = FINALIZED / FAIL
- engine faults = ERROR / NULL result
- exact precedence: FAIL > WARN > PASS
- current manifest: 11 stable CRITICAL checks
- no WARN-producing rule implemented in Batch 10
- human review remains independent from automated QA
- QA never triggers rendering

Migration proof:
- v8 → v9 → v8 → v9 PASS
- representative Batch 0–9 rows/relationships/checksums/provenance preserved exactly
- foreign-key checks clean

Controlled proof:
- source Batch 9 proof copied, never mutated
- QA run a3df047e-ba08-467c-b248-c0d1ad407064
- FINALIZED / PASS
- 11/11 checks PASS
- repeated create reused same run
- independent review: PENDING → ACCEPTED
- render attempt count unchanged

Verification:
- Batch 10 targeted: 23/23 PASS
- full backend: 75/75 PASS
- frontend/UI: 10/10 PASS
- lint/build: PASS
- UI changes: none

Next permitted batch: Batch 11.
