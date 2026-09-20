# MVP1 reporting security review

## Access and data boundaries

Backend reporting requires trip_financials.read, trip_profitability.read, expenses.read, fuel.read, cash_advance.read and financial_review.read together. Restrictive overrides deny the whole report rather than fabricate zero costs or complete settlement. Owner/admin/manager/accounting roles are tested against the actual repository policy. Driver, dispatcher, maintenance, anonymous and cross-tenant requests are denied appropriately.

Reports use the existing runtime role with neither superuser nor BYPASSRLS privilege. Existing forced-RLS tables are retained; no new table or migration was introduced. Integration tests use the runtime connection and foreign-tenant filters. Membership, organization and user are refreshed after acquiring the shared organization lock, then permissions are rechecked.

Financial writers use the existing organization serialization contract. A concurrent correction integration test proves the report sees either the old state or the new state, not mismatched totals and rows. Fingerprints identify a result; they do not create transaction consistency. Locks have bounded waiting and calculations have explicit deadlines.

## Exports and browser state

CSV authorization is reevaluated on every request. Complete bounded exports contain scope and financial qualifications. All text is NFKC-normalized, control characters removed and prefixed with an apostrophe; CSV quoting handles delimiters and quotes. Monetary output has a separate strict signed-decimal validation path so legitimate negative amounts remain numeric. Import/re-save behavior differs across spreadsheet applications; users are warned not to strip the safety prefix or enable external content. No universal spreadsheet-execution guarantee is claimed.

Print output HTML-escapes text and uses a restrictive CSP. It is a browser print view, not an automated PDF service. No public financial-report links or storage objects are created.

API responses are no-store. Report fetches explicitly use no-store and are not eligible for the Driver App's offline-cache path. Client snapshots are keyed by organization, report and filters; the prior organization's result disappears before another request completes. Logout and organization switching preserve existing app behavior.

## Demo ingress

A separate authenticated HTTPS tunnel targets the new local demo web server. The API accepts only its exact configured origin for mutations; CSRF is not disabled and no wildcard origin is used. HTTPS-origin sessions receive Secure cookies even in the explicit local-demo runtime. This does not make the tunnel a production deployment.

The old Windows application and old public link were not replaced. No firewall was disabled to bridge WSL to Windows. The temporary demo uses a WSL-built artifact with lock-matched Windows dependencies because the private-interface connection from WSL was not available. New Docker database provisioning hit a tool safety block and was not retried through another command. Existing isolated test storage was used independently.

## Remaining security/release gates

A public demo pass does not certify production infrastructure, independent penetration testing, remote recovery, deployed isolation, monitoring, storage IAM or physical iOS/Android behavior. No protected branch merge or production promotion is authorized by this report.

References: https://owasp.org/www-community/attacks/CSV_Injection ; https://www.postgresql.org/docs/current/ddl-rowsecurity.html ; https://www.postgresql.org/docs/current/explicit-locking.html
