# Batch 7 source audit

The Batch 6 source retains the reported Next.js/FastAPI/PostgreSQL architecture, private storage, RBAC/forced RLS and locked design. Historical Phase 0 proposals are not implemented authentication: the authoritative implementation uses hashed opaque database sessions, not OIDC. Earlier POD documents describe local-only storage; Batch 6's adapter and production-storage guide supersede that historical limitation.

Driver pages use server identity guards and existing shared TripDetail, DriverTrips, DeliveryPanel, SignatureCapture and MobileBottomNav. The manifest has name/colors/scope but no icons. There is no service worker, IndexedDB layer, persistent queue or offline authentication. Current delivery form state is memory-only. Ordinary fetch redirects on session expiry. Reload offline cannot currently render authorized driver pages.

Trip.version, expected_version, organization write locks, immutable milestones and database workflow guards already exist. Delivery commands explicitly commit before responding and compensate uncommitted evidence. Retries currently conflict rather than replay a durable result. These are retained and extended, not replaced.

Plan: a non-personalized cached shell reuses existing components; controlled IndexedDB stores only the current authorized driver projection and pending evidence. Durable actor/tenant-scoped command receipts commit atomically with existing commands. Reconnect reauthorizes before replay; stale versions stop dependent work. Browser data is untrusted and is not encrypted at rest. No owner data or authenticated HTML/API responses enter service-worker caches.

Pre-change source hashes: ignored .runtime/batch7-baseline.json. Existing design tokens, six locked assets and golden assertions remain the baseline. Batch 6 production/container/remote CI/physical-device/load limitations remain UNVERIFIED until executed.

Baseline status clarification: the actual BATCH-6-REPORT.md declares CONDITIONAL PASS, not an unconditional production PASS. Its deployment/device/container/independent-assessment limitations are preserved.
