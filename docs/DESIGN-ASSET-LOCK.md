# FleetPilot asset analysis and visual reference lock

**Status: LOCKED v1.** User instruction: “Analyze this assets, save and lock.” All six original JPEGs are preserved in [assets/design-references/v1](../assets/design-references/v1/manifest.json), with source names, dimensions, sizes and SHA-256 checksums. The lock applies to the saved reference baseline and documented design direction. No application redesign or feature activation is part of this change.

## Asset analysis

| Photo | Dimensions | Analysis and authority |
| --- | --- | --- |
| 1 | 1280 × 960 | Brand identity board. Primary authority for the mint F/road mark, wordmark, palette, voice, logo treatment and typography family. |
| 2 | 1280 × 853 | Owner overview: navy sidebar, light workspace, compact KPI cards, attention queue, fleet/status panels, recent trips and responsive owner mobile concept. Marketing surround provides mood rather than application chrome. |
| 3 | 1280 × 960 | Product design board: login, owner overview, fleet map, dispatch, trip detail, finance, AI and mobile patterns. Primary source for product spacing, radii and type hierarchy where legible. Feature illustrations are future references, not delivery scope. |
| 4 | 1280 × 1169 | Driver board: focused next action, clear route/stop details, vertical progress, recipient/photo/signature capture, issue reporting and bottom navigation. Primary driver visual reference. |
| 5 | 1280 × 960 | Same visible product-board composition as Photo 3, with a different binary file. Preserve as a companion reference rather than inventing a meaningful design revision. |
| 6 | 1280 × 853 | Dark trip-profitability concept, with cyan arrow/paper-plane-style logo and different navigation. Preserve for composition and future financial storytelling; it does not supersede the primary mint F mark or light owner workspace. |

## Locked primary design direction

- Logo: flowing mint F with a road cutout; Fleet in navy on light backgrounds or white on dark, Pilot in mint. Horizontal, stacked, symbol-only, monochrome and reverse variants are shown. Preserve proportions and clear space; no stretching, rotation, recoloring or added effects. These boards do not supply standalone vector masters or measurable clear-space specifications.
- Primary tagline: **Run the fleet. Not the chaos.** Supporting phrases include “Move smarter. Go further.” and driver-oriented “Your next stop, made simple.” Use them as brand copy references, not invented operational claims.
- Typeface: **Inter**, clean and readable, with a strong but restrained heading hierarchy and tabular numerals for operational figures.
- Owner UI: navy navigation, cloud background, white cards, fine borders, restrained shadows, compact data grouping and clear action hierarchy. Mint indicates primary action/positive progress, blue supports links and information, amber indicates attention, red indicates problems. Text and icons must communicate state in addition to color.
- Driver UI: mobile-first single-column flow, prominent next action, large touch controls, readable status/timeline, simple forms and persistent bottom navigation. Photo 4 governs driver composition; owner mobile concepts in Photos 2/3/5 are not substitutes for driver navigation.
- Icons: coherent, minimal outline family with consistent size/stroke. Prefer meaningful fleet, dispatch, driver, finance and settings symbols to decorative detail.
- Voice: calm, concise, intelligent, operational and confident. Emphasize clarity, control and practical outcomes.
- Photography: trucks, roads and mountain landscapes support brand/marketing surfaces. They should not obscure operational content or become fabricated live fleet imagery.

## Palette

Use printed token labels and the existing token source, rather than sampling JPEG pixels affected by gradients/compression.

| Token | Hex |
| --- | --- |
| Midnight Navy | `#08111F` |
| Slate | `#162235` |
| Electric Mint | `#2BE0A7` |
| Signal Blue | `#3B82F6` |
| Amber | `#F5A524` |
| Alert Red | `#F04444` |
| Cloud | `#F6F8FA` |

White remains the existing surface utility color. Current implementation tokens are in [packages/ui/tokens.css](../packages/ui/tokens.css); this task does not change them. Existing contrast safeguards, such as navy text on mint buttons, remain required even when concept artwork uses white text.

## Interpretation and conflicts

1. **Typography scale:** Photo 1 shows a presentation/brand H1 at 48/56; Photos 3/5 show product H1 32/40, H2 24/32, H3 18/28, body 16/24, caption 14/20 and small 12/16. Treat these as presentation versus product contexts, not an instruction to make every app heading 48 px. Numeric styling is semibold/tabular. Existing accessible implementation tokens remain unchanged until a scoped implementation task.
2. **Spacing/radii:** Photos 3/5 show an 8-point layout rhythm with a 4 px substep and examples 4/8/16/24/32; corner-radius examples are 4/8/12/16. These are reference values, not pixel measurements inferred from compressed screenshots.
3. **Alternate brand:** Photo 6's cyan arrow mark and dark application surface conflict with the repeated primary identity. Keep the entire image locked as an alternate concept; do not merge logos or silently switch the product theme.
4. **Illustrated workflows:** Mockup labels such as Assigned, Unloading or Completed are concept UI, not authority to replace the verified trip state machine. DELIVERED remains distinct from COMPLETED; POD policy, owner review, immutable history and authorization remain intact.
5. **Illustrated features:** AI, GPS/maps, finance/profitability, expenses/fuel, maintenance, OTP/social login and notifications shown in the boards do not authorize implementation. Figures, names, profit percentages, truck positions and alerts are sample artwork, not application data. The approved Batch 5 stop condition remains in force.
6. **Source limitations:** JPEG boards are flattened raster references. No editable Figma file, vector logo, standalone icon set or layered production artwork was supplied. Tiny captions can be ambiguous; do not derive exact component geometry or promise pixel-identical production assets from these boards.

## Preservation and future changes

Originals are locally read-only and checksum verified. This is a versioned reference lock, not cryptographic write prevention or an external backup. The [asset README](../assets/design-references/README.md) defines verification and revision handling. The existing public brand-reference image and running application remain unchanged. Further visual implementation should cite a reference ID and preserve verified functionality; changes to the primary identity or this baseline require a new explicit user instruction.
