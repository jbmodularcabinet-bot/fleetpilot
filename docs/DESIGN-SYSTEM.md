# Approved design system

## Locked reference baseline

The six newly supplied visual assets are saved and locked as v1. See [DESIGN-ASSET-LOCK.md](DESIGN-ASSET-LOCK.md) for analysis, palette, reference precedence and conflicts, the [FleetPilot UI Source of Truth](FLEETPILOT-UI-SOURCE-OF-TRUTH.md) for implementation precedence and Intelligence/Reports integration rules, and the [asset index](../assets/design-references/README.md) for originals and checksum verification. The primary brand remains the mint F/road mark and light owner workspace; the dark profitability board is retained as an alternate concept. Locking these references does not activate pictured features or replace verified lifecycle/security rules.

## Historical Batch 2 implementation notes

The shell availability and disabled controls described below reflect Batch 2. Current operational behavior is documented in the Batch 3–5 reports and actual source; these historical notes must not disable implemented Trips, POD or master-data workflows.

Visual authority remains the supplied owner and driver references. Batch 2 implements their application structure, not the promotional captions around the screenshots. No new logo was drawn: the original owner reference is bundled and CSS crops its existing logo. This is a temporary asset packaging choice until standalone approved artwork is available.

Tokens live in `packages/ui/tokens.css`. Core palette: Midnight Navy `#08111F`, Slate `#162235`, Electric Mint `#2BE0A7`, Signal Blue `#3B82F6`, Amber `#F5A524`, Alert Red `#F04444`, Cloud `#F6F8FA`, White `#FFFFFF`. Spacing, type sizes, radii, shadows and semantic text/background colors are centralized. Inter font files are bundled locally through `@fontsource/inter`; rendering does not fetch Google Fonts.

Owner shell: navy sidebar; organization/account top bar; greeting/date; five KPI cards; left revenue panel; right fleet/recent-trip panels; bottom AI Brief. Overview and Settings work. Operational navigation is visibly disabled. All metrics use em dashes, neutral rings and explanations; no sample financial figures are presented as data.

Driver shell: branded header, greeting, current trip empty card, disabled primary action, three disabled shortcuts, next-trip placeholder and five bottom tabs. Home and Profile work; Trips/Expenses/Alerts are disabled. There is no fabricated truck assignment, ETA or distance.

Reusable foundation components: FleetPilotLogo, Card, KpiCard, PageHeader, StatusBadge, EmptyState, LoadingState, ErrorState, DriverPrimaryAction, Sidebar, TopNav and MobileBottomNav. Forms have accessible labels; status is textual; controls have visible keyboard focus. Primary mint buttons use navy text for contrast. Empty KPI icons remain neutral because there is no health/status data.

Verify desktop at 1440 px, laptop at 1024 px and driver at 360/390/430 px. Sidebar collapses on narrow displays. The driver shell is constrained to 430 px on desktop and fills mobile width. Touch controls are at least 44 px tall. Reduced-motion preference disables spinner animation.
