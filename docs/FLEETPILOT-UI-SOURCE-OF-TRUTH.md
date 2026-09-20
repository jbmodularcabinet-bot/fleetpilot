# FleetPilot UI Source of Truth

**Status:** LOCKED IMPLEMENTATION GUIDANCE
**Asset baseline:** `assets/design-references/v1`
**Purpose:** Prevent visual drift while preserving verified FleetPilot functionality, financial controls, lifecycle rules, authorization, tenant isolation and auditability.

This document does not replace `DESIGN-ASSET-LOCK.md`. It defines how the locked visual references must be interpreted when implementing or reviewing FleetPilot screens.

## 1. Authority hierarchy

1. **FP-REF-01 — Brand identity:** authority for logo, primary palette, typography family and brand treatment.
2. **FP-REF-03 / FP-REF-05 — Product design boards:** primary authority for desktop product composition, spacing, density, card language, hierarchy and screen patterns.
3. **FP-REF-04 — Driver app:** primary authority for driver mobile composition, next-action hierarchy, trip progress, forms and bottom navigation.
4. **FP-REF-02 — Owner dashboard:** authority for owner overview composition and responsive direction.
5. **FP-REF-06 — Dark profitability concept:** composition/storytelling reference only; it does not supersede the mint-F identity or light owner workspace.

If a visual reference conflicts with verified application behavior, security, data integrity or lifecycle rules, the verified product behavior wins. Resolve the visual conflict without weakening the control.

## 2. Canonical visual language

- Navigation: Midnight Navy sidebar or shell.
- Workspace: Cloud/light background with white operational cards.
- Primary accent: Electric Mint.
- Supporting information: Signal Blue.
- Attention: Amber.
- Problem/critical state: Alert Red.
- Typeface: Inter with readable operational hierarchy and tabular numerals for financial/metric values.
- Surfaces: restrained borders/shadows; no decorative chrome that competes with operational data.
## 3. Product versus marketing imagery

The application must implement the product UI shown inside the reference boards, not the surrounding promotional composition.

Marketing imagery may guide storytelling, device framing, photography and sales presentation, but must not introduce:
- alternate navigation,
- decorative gradients as core application chrome,
- unverified features,
- fabricated live positions,
- invented financial results,
- alternate logos,
- or lifecycle states that conflict with the verified domain model.

Project-source boards analyzed outside the repository are **supplemental/advisory** until their originals are added to a new versioned asset set with file metadata and checksums. They must not silently supersede the locked v1 files.

## 4. Owner information architecture

The owner experience should read as one connected operating system:

`Dashboard → Intelligence → Reports → Operational record/detail → Action`

Primary operational domains remain:
- Live Fleet
- Dispatch
- Trips
- Drivers
- Vehicles
- POD / Delivery Evidence
- Expenses / Cash Advances
- Maintenance
- Finance / Profitability
- Alerts / Exceptions
- Settings / Access
## 5. Intelligence and Reports integration

New Intelligence and Reports screens must look native to the Owner Command Center rather than a separate analytics product.

Required rules:
- Reuse the owner sidebar, top bar, page header, cards, status badges and typography.
- Lead with exceptions, contribution, variance and decisions; avoid decorative dashboard clutter.
- Every important metric should have a traceable drill-down to the authoritative trip, driver, vehicle, expense, POD, maintenance or financial record.
- Contribution-based dashboard cards must state the metric name, value, time window and underlying scope.
- Reports must preserve existing financial-finalization and approval semantics.
- AI/insight copy must distinguish observation, recommendation and verified record.
- Empty/loading/error states must remain explicit.
- Demo/sample data must be clearly identifiable as sample/demo data and must never be represented as production financial truth.

### Six-report visual pattern

Each report should use the same shell and common structure:
1. Page title + reporting period/filter context.
2. Compact KPI summary.
3. Primary table or chart.
4. Exceptions / variance / contribution area.
5. Evidence or drill-down link to source records.
6. Export/action controls only when the underlying function is implemented and authorized.

Do not create six unrelated visual systems for six reports.
## 6. Driver experience

Driver screens remain mobile-first and task-first:
- one dominant next action,
- large touch targets,
- clear trip/stop sequence,
- obvious offline/sync state where applicable,
- minimal information density,
- persistent bottom navigation,
- evidence capture that preserves POD and audit rules.

Desktop owner responsive layouts must not replace the dedicated driver interaction model.

## 7. Visual QA contract

For every new or materially changed FleetPilot screen:
- cite the governing reference ID in the implementation/verification note;
- verify owner desktop at 1440 px and 1024 px;
- verify driver at 360, 390 and 430 px when driver UI is affected;
- verify status is communicated by text/iconography, not color alone;
- verify primary mint controls retain accessible contrast;
- verify no alternate logo/theme has been introduced;
- verify sample artwork values have not leaked into production data paths;
- verify screen behavior still matches authorization and domain rules.

## 8. Change control

The locked v1 JPEGs are immutable references. Do not overwrite them.

A future approved visual revision must:
1. create a new versioned asset directory;
2. preserve originals byte-for-byte;
3. record dimensions, byte sizes, source names and SHA-256 hashes;
4. explain what the new version supersedes;
5. update this source-of-truth only after the new assets are verified.

Until then, this document plus `DESIGN-ASSET-LOCK.md`, `DESIGN-SYSTEM.md`, the v1 manifest and verified application behavior are the FleetPilot UI implementation authority.
