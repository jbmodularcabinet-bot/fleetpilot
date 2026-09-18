# Profitability finalization policy — Batch 14

This replaces Batch 13's automatic FINAL rule. Historical Batch 13 reports remain records of their verification, not current policy.

FINAL requires COMPLETED trip + reviewed effective revenue present + all active included direct costs/revenue reviewed + all applicable cash advances SETTLED (safely voided advances excluded) + no unresolved reconciliation conflict + latest financial review APPROVED. Otherwise PROVISIONAL. Review and calculation share the same policy. Previously completed/reviewed trips do not receive automatic or migrated approval.

Revenue minus reviewed effective direct expense = contribution. Margin = contribution/revenue ×100, rounded with Decimal ROUND_HALF_UP. Zero revenue has null margin. Negative contribution is retained. Advance issuance, cash return, application and reversal add no separate direct cost or profit/loss. Maintenance remains excluded. Existing broader operational expense totals remain labelled and unchanged.

Example: revenue 20,000; issued advance 5,000; Fuel 2,500 + Toll 700; return 1,800. Direct cost 3,200, contribution 16,800. Zero outstanding makes the trip ready, but it remains PROVISIONAL until explicit approval. A later +500 cost overlay changes contribution to 16,300 and invalidates approval. A fresh review restores FINAL if all conditions pass. Partial case: issued 5,000, applied 3,000, returned 1,000 => outstanding 1,000; approval is rejected.

FINAL is operational financial review, not net profit, cash collection, tax, an accounting close, an invoice or audited financial statements. Device/staging/production readiness remains separately UNVERIFIED. Old unreviewed completed expenses remain blockers: this batch does not reopen ordinary closed-trip expense review or fabricate approval for missing data.
