# FleetPilot read-only client demo access

Status: verified temporary client-demo access for the local/public demonstration runtime.

- Username: `client.demo@fleetpilot.ph`
- Access profile: `CLIENT_DEMO_READONLY`
- Base role: `MANAGER` with restrictive deny-only overrides.
- Password: generated randomly and stored only at `C:\Users\User\Documents\ChatGPT\FleetPilot\.runtime\client-demo-credentials.json`.
- The credential file is runtime-only and ignored by Git. The password is not logged or committed.
- Owner credentials are not read, reset, or reused by the provisioning workflow.
- Scope: Demo Logistics Corp. only. Existing tenant context and forced RLS remain authoritative.

Allowed capabilities are limited to organization/read, owner dashboard, trips/read, trip financials/read,
trip profitability/read, expenses/read, fuel/read, cash advance/read, and financial review/read.
All other Manager permissions are explicitly denied by `permissions_json.deny`, including mutations,
financial approvals, settlement, organization/user administration, audit access, dispatch changes,
maintenance changes, evidence upload, and financial corrections.

The four retained September 21–24, 2026 validation trips remain the demo cohort. They are labelled
SYNTHETIC VALIDATION DATA and continue to be excluded from business reporting. Provisioning creates
only an authentication user, membership, restrictive access metadata, and audit entries; it does not
modify trip, revenue, expense, advance, review, or owner credential records.

Verification evidence is retained under `.runtime/batch16/`, including:
- `client-demo-pre.json` and `client-demo-final-db.json` — owner/sample source immutability.
- `client-demo-public-result.json` — public HTTPS read-only browser checks.
- `demo-security-performance.json` — public origin/session/security checks.
- `client-demo-access-final.xml` — isolated backend regression results.

This is temporary demo access, not a production deployment or a permanent public account.
