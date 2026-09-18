# Batch 8 baseline audit

Audit completed before implementation. Source confirms Batch 7's durable actor-scoped command receipts, shared IndexedDB queue, optimistic trip versions, private evidence abstraction, bounded image validation, forced PostgreSQL RLS and locked UI. No expense, fuel or monetary-total domain exists. Existing Decimal fields cover physical quantities, not money. Vehicle odometer is master data; no fuel update is currently performed.

Batch 6 and 7 are CONDITIONAL PASS, not production certification. Historical test counts are evidence from the reports, not a newly executed regression. Older lifecycle documentation is superseded by Batch 5's evidence-gated delivery; preserve that implementation. No architecture replacement is needed.

Design baseline: original six references verified; file hashes saved in ignored .runtime/batch8-baseline.json. Preserve packages/ui primitives/tokens, Inter, navy sidebar, cloud workspace, existing Trip Detail and Driver bottom navigation. Existing tests/e2e/design-v1.ts remains the visual contract. Only expense forms, receipt/history/review and fuel history are additions.

Plan: explicit immutable financial revisions; PHP Decimal amounts serialized as strings; server ROUND_HALF_UP fuel calculation; conservative trusted-odometer blocker; private receipt authorization; existing trip serialization/versioning and durable replay. Operational cost inputs do not imply accounting expense or profitability. Production, physical-device, Safari and load verification remain UNVERIFIED unless executed.

Deployment discrepancy verified during final gates: the isolated test database had migration 0006 while the development database remained at 0005. After all 307 local tests passed, development was upgraded forward through 0006 to 0007 head. No development downgrade/reset was performed. Production deployment remains UNVERIFIED.
