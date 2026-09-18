# Trip state machine — deferred

Historical Batch 2 note. Batch 4 implements the resolved workflow in [TRIP-LIFECYCLE.md](TRIP-LIFECYCLE.md); use that document for current behavior.

No trip entities, enums, transition endpoints or workflow engine are implemented in Batch 2.

Phase 0 identified pickup arrival and loading-complete milestones missing from the canonical state sequence. Preserve that question for the trip-core batch. Do not silently change the master states or encode proposed workflow rules in placeholder UI.
