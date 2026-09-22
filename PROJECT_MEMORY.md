# CreativeOS Project Memory

Product: CreativeOS Studio — Local V1.
Mission: local-first AI creative production OS for SaaS marketing campaigns.
Golden projects: FleetPilot (primary), SmartRoom, JB Cabinet OS.
Core flow: Objective → Audience → Offer → Brand Brain → Creative Director → Script → Storyboard → Asset Assignment → Routing → Queue → Review → QA → Composition → Export.

Architecture lock:
- React + TypeScript frontend.
- Tauri desktop wrapper preferred.
- SQLite local persistence.
- Local filesystem assets.
- FFmpeg composition/export.
- Provider adapter layer for LLM/image/video/voice.

Hard product rule: any asset marked immutable_ui=true must never enter a generative image/video pipeline.
Approved UI is composited/animated only.

Design source of truth:
- ../V1_UI_AE/DESIGN-SPEC.md
- ../V1_UI_AE/DESIGN-PASS-02.md
- ../V1_UI_AE/CREATIVE-DIRECTOR-STORYBOARD-SPEC.md
- ../V1_UI_AE/build_creativeos_v1.jsx


Batch 7 lock:
- generation_jobs remains creative request/provenance authority.
- generation_queue is authoritative for scheduling and execution lifecycle.
- generated_assets remains immutable output provenance.
- Queue retries reuse the same generation job and queue record.
- MOCK is the only enabled provider by default; live provider routes refuse execution until configured.
- Atomic claim + claim_token + lease recovery are required invariants.


Batch 8 lock:
- Cost intelligence is advisory evidence, never queue execution authority.
- Authoritative money is integer minor units with ISO currency + explicit minor exponent.
- FX conversion requires an immutable explicit snapshot and uses Decimal ROUND_HALF_UP.
- Missing budget, pricing, currency, quantity, or required FX is UNKNOWN, never zero.
- Historical profiles, FX snapshots, recommendations, estimates, and overrides are append-only evidence.
- Budget override cannot bypass capability, provider-enable, immutable-UI, or security constraints.


Batch 9 lock:
- Voice is deterministic MOCK only until a later explicitly authorized live-provider batch.
- voice_jobs owns local voice request/output provenance.
- composition_timelines + composition_timeline_entries own deterministic media ordering/timing.
- render_jobs owns authoritative render identity/result; render_attempts preserves per-attempt diagnostics.
- FFmpeg execution must use validated argument arrays with shell=False; stored metadata is never executable shell input.
- Preview outputs stay under the approved generated-output root and never overwrite source assets.
- Successful identical render identity is reused; source-file hashes participate in render identity.
- ffprobe verification, source checksum protection, and 0.20s duration tolerance are required Batch 9 invariants.


Batch 10 lock:
- Deterministic QA is read-only with respect to render provenance and execution.
- qa_runs owns immutable automated evaluation identity/lifecycle/aggregate result.
- qa_check_results owns immutable per-check evidence.
- qa_reviews owns human review state independently.
- Base QA identity excludes attempt number; explicit ERROR retries share the base identity and receive incremented attempt_version.
- Repeated create returns canonical attempt 1; repeated retry of one ERROR returns the same direct successor.
- Required manifest v1 has 11 stable CRITICAL checks.
- Aggregate precedence is FAIL > WARN > PASS; incomplete/malformed required evidence cannot pass.
- Artifact defects finalize FAIL; QA engine execution failures end ERROR with null result.
- Batch 10 defines no WARN-producing rule.
- QA cannot trigger render/retry/publishing actions.
