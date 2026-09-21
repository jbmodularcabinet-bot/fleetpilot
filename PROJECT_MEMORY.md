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
