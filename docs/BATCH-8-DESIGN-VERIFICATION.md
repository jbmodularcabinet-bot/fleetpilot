# Batch 8 design verification

Baseline: .runtime/batch8-baseline.json and six read-only original references verified before implementation. Existing packages/ui tokens/components, globals.css, Inter, logo/brand artwork and primary navigation are unchanged. Photo 6 remains alternate reference, not adopted.

Necessary additions only:

- Owner/Driver Trip Detail: expense card after original trip details and milestone timeline. Existing POD, next-action hierarchy, trip fields and timeline are retained. Category/decimal/date/vendor/notes/receipt form uses current labels, inputs, buttons and cards. Owner explicit review/correction/void confirmation and revision/evidence history use the same primitives.
- Vehicle detail: paginated real Fuel history card, no efficiency or financial analytics.
- Existing Driver sync list: expense category/amount and receipt filename labels, using existing saved/syncing/needs-attention states. No new navigation or queue UI template.

Driver bottom navigation remains Home/Trips/Profile with the existing disabled Expenses/Alerts placeholders. Expense entry is inside Trip Detail as requested. No core CSS/token/logo/icon/font, gradients or unrelated screens were changed. No fake metrics or profitability section was introduced.

Verification includes original-asset integrity, production browser inherited design assertions, online owner/driver expense workflow, phone-width overflow check, offline restored expense workflow and captured screenshots. Existing unrelated golden assertions were not changed. Final results and screenshot paths are in BATCH-8-REPORT.md; physical-device/pixel-exact reference reproduction are not claimed.

Upload retry fields use React state for rendered disabled behavior; refs only preserve the stable operation key/result inside event handlers. This was corrected after lint identified render-time ref access. Success/error/loading and receipt retry states use existing styles.

Existing offline empty-state wording now says “Offline · no pending actions” until a real queued commit exists. It previously said “0 actions saved locally,” which could be mistaken for a completed save. Two unit checks and the unchanged POD reopen assertion verify this necessary state correction.

Final result: DESIGN LOCK PASS. Six original assets verified, all 31 production-Chrome browser tests passed and final owner/driver screenshots visually inspected. Owner screenshot is 390 pixels wide; the reopened driver screenshot is a desktop viewport rendering the existing narrow driver shell, while expense capture also ran at 390 pixels. Neither is physical-device certification.
