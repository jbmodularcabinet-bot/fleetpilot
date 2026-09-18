# Cash advance settlement — Batch 14

A cash advance funds a driver's trip expenses; it is not itself direct cost. The authoritative model uses PHP NUMERIC/Decimal and existing tenant context, organization serialization, audit and durable command receipts. No ledger, payroll, reimbursement or bank reconciliation is introduced.

## Records and history

`cash_advances` is immutable: tenant, trip, driver snapshot, issued amount/currency, purpose, issuance actor/time and optional source expense. New issuance derives the assigned driver. Reconciliation of a captured DRIVER_CASH_ADVANCE derives the original expense driver and current effective amount; cross-trip/tenant references are rejected.

Existing Batch 8 category records remain untouched. They represent captured inputs, not independently confirmed cash issuance. An owner/operator explicitly chooses **Reconcile recorded advance** to adopt one exactly once into the settlement domain. This accepts an active captured record, including SUBMITTED, because the privileged adoption is the issuance confirmation; it does not claim that the source expense was reviewed. Unreconciled active category records block financial approval. Old/offline clients may continue capturing this category; they cannot silently evade finalization. New direct issuance does not create an expense row.

`cash_advance_settlement_entries` is append-only. EXPENSE_APPLIED references an existing effective REVIEWED, non-voided, non-advance expense for the same trip and original driver. The server derives the entire amount: no invented total or partial allocation. One expense may have at most one active application across advances. CASH_RETURNED accepts a positive PHP amount. REVERSAL references one prior unreversed expense application/return and copies its amount. VOID is a zero-valued explicit reasoned event.

Outstanding = issued − active expense applications − active cash returns. ISSUED has no active settlement, PARTIALLY_SETTLED has a positive residual, SETTLED has zero residual, VOIDED has a void event. Status and balance are derived server-side, never accepted from the client. A reversed allocation remains visible and can be applied again using its current eligible amount. No entry disappears.

## Safety

Source amounts are positive decimal strings, at most two places, <=10,000,000 PHP. JSON floats, signs, exponent, overflow and extra monetary precision are rejected. Settlement cannot exceed the balance. Existing organization locks serialize independent requests; database triggers independently reject over-return/double application/invalid source/actor and enforce immutable history. Idempotency-Key is mandatory: identical actor/key/body replays the original result, changed body conflicts, and permission is refreshed before replay. Atomic audit/receipt failure rolls back settlement.

Void is allowed only when no settlement entry has ever existed, including reversed entries. An imported advance that is voided while its captured source remains active still blocks approval; explicitly reconcile the source through the existing permitted correction/void process. Issued amounts never silently follow later source corrections. A changed imported source creates a review conflict until the original source is explicitly reconciled. There is no arbitrary advance amount edit or driver reassignment.

An applied expense corrected below its allocated amount, voided, changed to advance or reset to unreviewed blocks approval. Reverse its allocation and reconcile at the new valid amount. An increase does not invent extra advance funding: the original applied snapshot remains unchanged and the increment is not allocated to the advance. Contribution still reflects the full reviewed expense once.

## Permissions and interface

Owner/admin/manager/accounting may read/create/settle/void subject to restrictive overrides. Only owner/admin may approve financial review. Drivers have no new advance or settlement authority or detail endpoint access; they retain their existing own-expense capture. No contribution or margin is added to Driver App/offline caches.

Trip Detail retains the existing visual system. The small settlement section displays issued/applied/returned/outstanding/status, actor/time/reason history and native forms with confirmation. Advance lists are paginated; expense choices page through 100 records; a selected advance's history is currently unpaginated. No new navigation or chart.

API: GET/POST `/api/v1/trips/{id}/cash-advances`; POST `/cash-advances/{id}/apply-expense`, `/cash-return`, `/void`, `/entries/{entry_id}/reverse`. All commands are online-only. Cancelled trips are read-only. Completed trips may receive this explicit financial workflow without reopening operational fields or changing Trip.version.

Golden: 5,000 issued; reviewed Fuel 2,500 + Toll 700 applied; 1,800 returned; zero outstanding. Direct cost remains 3,200, not 8,200. With 20,000 revenue, contribution is 16,800.

The backward-compatible financial API field `excluded_cash_advances` still describes captured advance expense-category amounts only. It is not a total of dedicated issuance. The UI uses explicit exclusion policy text and displays real issuance/balances in the settlement section, avoiding a misleading combined total.
