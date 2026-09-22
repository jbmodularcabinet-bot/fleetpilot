# FleetPilot MVP1 — Intelligence & Reports release handoff

Date: September 20, 2026. **Client demo: PASS. Production release: BLOCKED.**

The new dashboard, Intelligence and six reports are implemented and working through a separately verified authenticated HTTPS demo. This supersedes the earlier blocked-baseline handoff, preserved privately at .runtime/batch16/prior-blocked-release-handoff.md. It is not production certification.

## Provenance

Batch: 16.
Authoritative development repository: /home/user/projects/fleetpilot.
Branch: feature/mvp1-intelligence-reports.
Starting commit: 912f37ac0ec5a1f81e1f0118b7bbacb3617aa7e8.
Preserved prerequisite commit: 65b7224a824683a7573a006bbaf19758325982db.
The final feature SHA, remote workflow URLs and final observed gates are recorded in .runtime/batch16/RELEASE-RESULT.json and the external execution handoff after publication. A document cannot embed its own eventual commit hash.

All 342 starting source files were preserved and hash-verified. The 24 pre-existing Batch 15 prerequisite files were committed separately from Batch 16. Three unrelated Creative OS capture files remain outside this release. The Windows source/reference application was not overwritten.

## Implemented and demonstrated

| Gate | Result |
|---|---|
| Intelligence | PASS — deterministic rule evidence, prioritized findings and authorized source links |
| Six reports | PASS — six distinct filtered views, complete bounded CSV and print-ready output |
| Owner Dashboard | PASS — live reviewed contribution metrics and supporting owner panels |
| Policy settings | PASS — tenant settings, validation, owner/admin authorization and audit integration tests |
| Financial reconciliation | PASS — actual retained four-trip totals 74,000.00 / 40,250.00 / 33,750.00 / 45.61% |
| Advance distinction | PASS — 5,000.00 captured, no confirmed issuance or inferred capture balance |
| Demo data preservation | PASS — original IDs, dates and operational/financial records retained; no reseeding |
| Tenant/RBAC checks | PASS in executed runtime/integration/public tests; not independent security certification |
| Export security | PASS in executed formula-text, HTML, authorization and download checks; spreadsheet caveats disclosed |
| Browser/mobile | PASS — 16 local and 16 public runs of the same workflows; six extra public security/performance checks |
| Frontend regression | PASS — 63 distinct tests, including same-route filter-navigation coverage |
| TypeScript/lint/build | PASS at the recorded web candidate check |
| Design preservation | PASS — six locked originals verified natively in WSL, plus reviewed desktop/mobile screenshots |
| Backend coverage | PASS — 460 distinct cases verified across the full invocation and ten-case environment rerun; initial failures retained |
| Full original browser regression | NOT RUN locally for this candidate; remote CI evidence is separate |
| Large-scale performance | NOT RUN — 1,000 trips / 10,000 expenses remains a release gate |
| New local Docker app/runtime | BLOCKED — new isolated provisioning was tool-blocked; no bypass was used |
| Production deployment/verification | BLOCKED — no authorized, verified production promotion target |

## Demo runtime

The source and web build are in WSL. The verified standalone web artifact runs with existing lock-matched Windows dependencies; the API runs the WSL source through the existing Windows Python runtime. This is an explicit hybrid local demo, not a claim that the Linux-native runtime migration is complete.

The new web server uses port 3500; the new API uses port 8016 on the selected private host interface. The original web/API ports 3000/8000 remain unchanged. The temporary public origin is stored in .runtime/batch16/authorized-demo-origin.json and is the API's exact allowed origin. No wildcard origin, CSRF disablement, public data bucket or production demo-tenant copy was introduced.

Keep the laptop, network, new demo web/API processes and tunnel running during the presentation. A tunnel restart may require a new origin and another login check. The public endpoint is authenticated; do not distribute an owner's credentials as a general client login.

## Owner walkthrough

Sign in with the existing demo-owner account. On Overview select **Demo: Sep 21–24, 2026**. Confirm the SYNTHETIC VALIDATION DATA banner, four PROVISIONAL trips, zero FINAL, reviewed revenue PHP 74,000.00, direct cost PHP 40,250.00 and contribution PHP 33,750.00 at 45.61% weighted margin.

Open Intelligence for the PHP -1,200.00 negative-contribution trip and its reviewed revenue/cost explanation. Open Direct Cost Analysis for Fuel PHP 24,150.00 / 60.00%; explain that concentration is not a theft or efficiency diagnosis. Open Cash Advance & Settlement for the separate PHP 5,000.00 unreconciled capture. Use Trip Contribution to drill into actual financial source records. CSV and print controls regenerate a fully scoped result with a calculation timestamp and fingerprint.

The demonstration shows reviewed direct trip contribution, not net profit or collections. No financial approvals or settlements were performed by the report engine.

## Remaining release action

Inspect exact-commit CI and resolve every remaining full-regression, runtime, scale, physical-device and authorized-production gate before promoting beyond the synthetic client demo. No protected branch merge or production deployment is part of this handoff.
