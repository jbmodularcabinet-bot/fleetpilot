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
