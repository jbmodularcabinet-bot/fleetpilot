# CreativeOS Agent Rules

1. Read PROJECT_MEMORY.md, CURRENT_STATE.md, and this file before modifying code.
2. Preserve approved architecture and UI locks unless a documented blocker exists.
3. Never fake live provider success; label MOCK vs LIVE explicitly.
4. Never commit secrets or print API keys in logs.
5. Never overwrite original assets or failed-generation history.
6. Never route immutable_ui=true assets through generative image/video providers.
7. Add tests with every feature; do not disable tests to obtain PASS.
8. FleetPilot-specific behavior must remain fixture/data-driven, not hard-coded architecture.
9. Provider complexity stays secondary in the normal creative workflow.
10. CreativeOS is not a generic chatbot; structured creative-production UI is primary.
11. Do not begin V2 automatically.
12. A batch is complete only after independent verification and memory updates.

Batch completion status must be exactly PASS, CONDITIONAL PASS, or FAIL.
Do not proceed after FAIL.
