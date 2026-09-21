# Architecture Decisions

## D-001 Local-first V1
CreativeOS V1 runs locally with SQLite, local asset storage, and optional external generation APIs.
Reason: fastest path to useful internal production while minimizing infrastructure cost.

## D-002 Provider adapters
All LLM/image/video/voice integrations sit behind provider-independent interfaces.
Reason: providers must be swappable without changing campaign logic.

## D-003 Immutable SaaS UI
Real approved SaaS UI can be transformed only through non-generative compositing/motion operations.
Reason: preserve product truth and prevent AI-distorted interfaces.

## D-004 Tauri target
Use Tauri for Windows packaging unless repository/tooling audit reveals a blocker.

## D-005 FFmpeg composition
FFmpeg is the V1 render/composition engine; Adobe tools remain optional production companions.

## D-006 Python stdlib SQLite backend
Batch 2 uses Python's standard-library sqlite3 module for local domain persistence.
Reason: avoids native Node SQLite build friction while preserving the approved local-first architecture; frontend remains React/TypeScript and can call this local backend through the desktop bridge in later batches.

## D-007 Brand Brain schema expansion
Batch 3 extends BrandProfile through additive migration v2 and adds creative_memory records.
Reason: keep brand identity, positioning, messaging, visual constraints, and UI-protection policy locally persistent without replacing Batch 2 architecture.

## D-008 Brand Brain UI draft persistence
Until the Tauri desktop bridge is introduced, the React Brand Brain screen stores its editable draft in browser localStorage while the authoritative Brand Brain domain/persistence layer remains SQLite.
Reason: preserve local-first usability in Batch 3 without prematurely introducing a new bridge or service architecture.

## D-009 Versioned Creative Director plans
Batch 4 adds `director_plans` through additive migration v3.
Reason: AI regeneration must create a new DRAFT proposal without overwriting previously approved creative plans.

## D-010 Provider-independent Creative Director
Creative Director logic targets a provider protocol with deterministic MOCK and explicit LIVE adapter states.
Reason: campaign planning must remain swappable across LLM providers and must never fake live execution when credentials are absent.

## D-011 Director UI draft persistence
Until the Tauri bridge is introduced, editable Director proposal state in React uses localStorage while authoritative generated/approved Director plans persist in SQLite.
Reason: keep Batch 4 local-first and testable without prematurely expanding desktop bridge scope.
