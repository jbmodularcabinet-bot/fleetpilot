# Batch 6 design verification

**DESIGN LOCK: PASS.** Source/asset integrity and all 17 production browser workflows passed, with no retries.

The actual Batch 5 implementation is authoritative. All six original references remain byte-identical and read-only; the manifest is unchanged. Photo 6 is alternate only. Photos 3 and 5 retain distinct files/hashes. No asset was regenerated, cropped, renamed, recompressed or replaced.

Pre-change SHA-256 inventory: ignored `.runtime/batch6-baseline.json`. Exact unchanged files independently checked: packages/ui/tokens.css, packages/ui/index.tsx, apps/web/src/app/globals.css, apps/web/src/components/navigation.tsx, trips.tsx, master-data.tsx, and apps/web/public/brand-reference.png. Seven files remain byte-identical after the final error-state change. delivery.tsx is the sole component exception described below.

Retained tokens: Inter 400/500/600/700; navy #08111F, slate #162235, mint #2BE0A7, blue #3B82F6, amber #F5A524, red #F04444, cloud #F6F8FA. Existing spacing tokens, 12px delivery-card radius, white cards/borders, navy owner sidebar, mint buttons, existing Lucide icons, status chips, forms, tables and white driver bottom navigation remain unchanged.

New tests/e2e/hardening.spec.ts covers owner dashboard, Customers, Vehicles, Drivers and Dispatch navigation/workspace/font/logo/overflow; driver home and assigned-trip list at 390px; unique response CSP nonces and no unsafe-inline scripts. Existing delivery golden tests retain rendered token/card/logo/navigation assertions and the attempt/POD/Trip Detail desktop/mobile checks. Existing screenshots are retained as review evidence; no pixel baseline was regenerated to mask changes.

Infrastructure-related frontend changes: root layout waits for a request so Next.js can attach CSP nonces; new proxy.ts sets per-response CSP/security headers; next.config.ts enables standalone output and removes the superseded broad script policy. No normal-state content, hierarchy, styling, icon, logo, typography or navigation change. Dynamic rendering trades static caching for per-request script security. Style-src unsafe-inline remains for existing React inline styles; production script policy allows neither unsafe-inline nor unsafe-eval.

One necessary failure-state addition: a rejected/missing evidence image previously left a broken thumbnail. EvidencePreview now uses the existing ErrorState and secondary button to explain unavailability and retry through the same authorized API. It affects owner/driver POD images only when retrieval fails; successful markup is unchanged. The old component had no image-error handler, so the recovery state could not be exposed without this small extension. Component tests simulate failure/retry. This is the explicitly permitted storage-error exception to the design lock.

Default expectation met: zero material design change. All three production browser runs passed all 17 tests; the final standalone run after the image-retry change took 5.8 minutes. Owner desktop and driver POD screenshots were visually reviewed; approved navy/light/mint layout remains intact. Evidence is retained under ignored .runtime/batch6-artifacts. Final outcomes are in BATCH-6-REPORT.md. Physical-device and pixel-identical raster reproduction are not claimed.
