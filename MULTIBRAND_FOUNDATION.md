# Multi-brand foundation — design and execution record

CreativeOS is a brand-agnostic production OS. HABI is a native ecosystem represented by data, never a platform dependency.

Inspection: master at c72c4548d9f7e3a3c04ff1061238bdefd11c0255; unfinished v11 changes were already staged. Baseline: 92 backend tests; 10 frontend tests; lint and production build passed. Preserve unrelated untracked scripts and backend/main.py.

Design: retain SQLite and existing pipeline services. Organizations own multiple Brand Brain profiles (BRAND or PRODUCT); campaigns own their strategy, scenes, assets, costs and governance. NATIVE/EXTERNAL and ecosystem_key are metadata. Existing unowned rows remain legacy local data; scoped connections cannot access them. A trusted host selects an authorized organization and brand when opening a scoped store; this change does not implement network authentication.

Add database ownership views and insert/update consistency triggers so linked records cannot mix campaigns/brands. Lock ownership links against reassignment, including indirect ancestors, to preserve historical evidence. Add scoped CRUD and filtering to the existing store and guard raw-SQL service entry points. Resolve Director Brand Brain from persistence. Validate export render lineage. Preserve provider injection and MOCK workflows; do not call live APIs.

Migration v11 is currently uncommitted and is completed here. Existing databases are not migrated by this task. Migration execution must be atomic. Rollback may remove v11 only when no organization data would be discarded.

Execution, directly via Remote Desktop Commander:
1. Add negative tests for cross-brand links, scoped read/write, legacy exclusion, Director spoofing and export/queue ownership; demonstrate failures.
2. Complete schema views/triggers and scoped store; test both brands in one organization and brands across organizations.
3. Guard service SQL bypasses and preserve provider abstraction; test existing generation, QA, human review and export.
4. Restore portable test fixtures where unfinished edits replaced them with machine-local proof files; retain all behavioral assertions.
5. Run full backend suite, frontend tests, lint/build, migration and integrity checks. Review diff; update project memory. Commit only verified task files.

No deployment, Agency Mode, publishing, performance ingestion or billing. No source proof databases or original assets are edited.

## Verified result ? 2026-09-30

PASS for the local backend foundation. All commands ran through Remote Desktop Commander on LAPTOP-MDRJATPA in the existing repository.
- Backend: python -m unittest discover -s tests -v ? 108 tests, OK, exit 0.
- Frontend: npm test ? 10 tests, exit 0.
- Lint: npm run lint ? 0 warnings, 0 errors.
- Build: npm run build ? TypeScript and Vite production build, exit 0.
- Integrity: migration round trips and foreign_key_check remain clean; injected v11 failure leaves v10 schema and data unchanged.
- Regression proof: the first isolation run exposed accepted mixed-brand links, history reassignment and caller-supplied Brand Brain content. Those regressions now pass.
- Provider proof: importing generation_engine does not import the Higgsfield adapter. LOCAL_TEST execution reaches READY_FOR_EXPORT through real rendering, 11 QA checks and explicit human approval.
- No tests were disabled. Restored portable fixtures preserve original golden-path assertions. Incoming machine-local fixture edits were backed up at C:/Users/User/AppData/Local/Temp/creativeos-test-intake-po1ttezh.

The caller must derive the authorized organization and brand from its trusted session before constructing CreativeOSStore(db, organization_id=org, brand_profile_id=brand). Supplying identifiers is not authentication. Raw conn access and unscoped connections are trusted internal capabilities. Local files remain within the existing filesystem trust model. The frontend remains the existing local V1 UI.

Recommended next phase: integrate authenticated organization/brand selection into the application, with an explicit legacy-data ownership migration. Performance learning stays a future extension; no ingestion or publishing was added.

## Changed files

- CURRENT_STATE.md
- MULTIBRAND_FOUNDATION.md
- PROJECT_MEMORY.md
- TEST_MATRIX.md
- backend/creativeos_db/__init__.py
- backend/creativeos_db/director_service.py
- backend/creativeos_db/domain.py
- backend/creativeos_db/generation_engine.py
- backend/creativeos_db/higgsfield_provider.py
- backend/creativeos_db/migrations.py
- backend/creativeos_db/multibrand.py
- backend/creativeos_db/provider_contract.py
- backend/creativeos_db/qa.py
- backend/creativeos_db/queue.py
- backend/creativeos_db/scope_schema.py
- backend/creativeos_db/store.py
- backend/tests/__init__.py
- backend/tests/repro_fixtures.py
- backend/tests/test_brand_brain.py
- backend/tests/test_cost_optimizer.py
- backend/tests/test_director.py
- backend/tests/test_generation.py
- backend/tests/test_generation_engine.py
- backend/tests/test_golden_path.py
- backend/tests/test_isolation.py
- backend/tests/test_media.py
- backend/tests/test_multibrand.py
- backend/tests/test_qa.py
- backend/tests/test_queue.py
- backend/tests/test_store.py
- backend/tests/test_storyboard.py
