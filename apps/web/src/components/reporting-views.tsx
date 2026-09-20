"use client";
import Link from "next/link";
import {
  AlertTriangle,
  Banknote,
  CircleDollarSign,
  ChartNoAxesCombined,
  ClipboardCheck,
  Percent,
} from "lucide-react";
import { Card, EmptyState, StatusBadge } from "@fleetpilot/ui";
import { php } from "@/lib/money";
import { human } from "@/lib/trips";
import {
  reportQuery,
  type ReportData,
  type Summary,
  type Finding,
  type Trip,
  type Customer,
  type Category,
  type Advance,
  type ReportName,
} from "@/lib/reporting";
const margin = (value: string | null) => (value === null ? "N/A" : `${value}%`);
export function ContributionMetrics({ value }: { value: Summary }) {
  const cards = [
    [
      "Reviewed Revenue",
      php(value.revenue),
      CircleDollarSign,
      "Reviewed operational charges",
      "positive",
    ],
    [
      "Direct Trip Cost",
      php(value.direct_cost),
      Banknote,
      "Reviewed direct expenses only",
      "neutral",
    ],
    [
      "Contribution",
      php(value.contribution),
      ChartNoAxesCombined,
      "Revenue less direct trip costs",
      value.contribution.startsWith("-") ? "critical" : "positive",
    ],
    [
      "Weighted Contribution Margin",
      margin(value.weighted_margin_percent),
      Percent,
      "Total contribution / reviewed revenue",
      "active",
    ],
    [
      "Negative-Contribution Trips",
      String(value.negative_count),
      AlertTriangle,
      "Trips with reviewed revenue and cost inputs",
      "critical",
    ],
    [
      "Trips Requiring Financial Attention",
      String(value.attention_trip_count),
      ClipboardCheck,
      "Provisional, incomplete or negative",
      "warning",
    ],
  ] as const;
  return (
    <div className="kpi-grid reporting-kpis">
      {cards.map(([label, amount, Icon, hint, tone]) => (
        <Card key={label} className={`kpi kpi-${tone}`}>
          <div className="kpi-top">
            <span className={`icon-box icon-box-${tone}`}>
              <Icon size={20} />
            </span>
            <span>{label}</span>
          </div>
          <div className="kpi-value" data-testid={label}>
            {amount}
          </div>
          <span className="small muted">{hint}</span>
        </Card>
      ))}
    </div>
  );
}
export function FindingCards({
  findings,
  query,
}: {
  findings: Finding[];
  query: Record<string, string>;
}) {
  if (!findings.length)
    return (
      <EmptyState
        title="No findings in this scope"
        description="No configured rule triggered. This does not certify that all business costs have been captured."
      />
    );
  return (
    <div className="reporting-findings">
      {findings.map((f) => (
        <article
          className={`reporting-finding priority-${f.priority.toLowerCase()}`}
          key={f.key}
        >
          <div className="reporting-finding-title">
            <StatusBadge tone={f.priority === "LOW" ? "neutral" : "warning"}>
              {f.priority}
            </StatusBadge>
            <h3>{f.title}</h3>
          </div>
          <p>{f.explanation}</p>
          <details>
            <summary>Supporting values and rule</summary>
            <p className="small">
              {f.rule_id} · {f.rule_version}
            </p>
            <p>{f.comparison_basis}</p>
            <pre className="reporting-evidence">
              {JSON.stringify(f.supporting_values, null, 2)}
            </pre>
            <p className="small muted">{f.qualification}</p>
            <p>{f.recommended_action}</p>
          </details>
          <Link
            className="button secondary"
            href={
              f.href.includes("?")
                ? f.href
                : f.href +
                  (f.href.startsWith("/reports/")
                    ? "?" + reportQuery(query)
                    : "")
            }
          >
            Review supporting records
          </Link>
        </article>
      ))}
    </div>
  );
}
export function CostBreakdown({
  categories,
  query,
}: {
  categories: Category[];
  query: Record<string, string>;
}) {
  if (!categories.length)
    return (
      <EmptyState
        title="No reviewed cost breakdown"
        description="Missing expense records do not establish zero operating cost."
      />
    );
  return (
    <div className="reporting-cost-bars">
      {categories.map((c) => (
        <div key={c.category}>
          <div className="reporting-cost-label">
            <strong>{human(c.category)}</strong>
            <span>
              {php(c.reviewed_total)} · {margin(c.share_percent)}
            </span>
          </div>
          <div className="reporting-bar-track">
            <div
              className="reporting-bar"
              style={{
                width: `${Math.max(0, Math.min(100, Number(c.share_percent ?? "0")))}%`,
              }}
            />
          </div>
          <details>
            <summary>
              {c.trip_ids.length} supporting trips · {c.unreviewed_count}{" "}
              unreviewed records
            </summary>
            <div className="reporting-source-links">
              {c.trip_ids.map((id) => (
                <Link
                  key={id}
                  href={`/reports/trip-contribution?${reportQuery(query, { trip_id: id })}`}
                >
                  Trip {id.slice(0, 8)}
                </Link>
              ))}
            </div>
          </details>
        </div>
      ))}
    </div>
  );
}
export function CustomerCards({ customers }: { customers: Customer[] }) {
  return customers.length ? (
    <div className="reporting-customer-list">
      {customers.map((c) => (
        <div key={c.customer_id}>
          <Link href={c.href}>{c.customer_name}</Link>
          <strong>{php(c.contribution)}</strong>
          <span className="small muted">
            {c.trip_count} trips · {margin(c.weighted_margin_percent)} weighted
            margin · {c.provisional_count} provisional
          </span>
        </div>
      ))}
    </div>
  ) : (
    <EmptyState
      title="No customer contribution in this scope"
      description="Select a period containing reviewed trip financial records."
    />
  );
}
export function ReportTable({
  name,
  data,
  query,
}: {
  name: ReportName;
  data: ReportData;
  query: Record<string, string>;
}) {
  if (name === "financial-exceptions")
    return <FindingCards findings={data.items as Finding[]} query={query} />;
  if (!data.items.length && name !== "executive-contribution")
    return (
      <EmptyState
        title="No matching records"
        description="Change the filters or use the labelled validation period. No performance conclusion is available for an empty result."
      />
    );
  if (name === "executive-contribution")
    return (
      <>
        <ContributionMetrics value={data.summary} />
        <div className="reporting-counts">
          <StatusBadge tone="positive">
            {data.summary.final_count} FINAL
          </StatusBadge>
          <StatusBadge tone="warning">
            {data.summary.provisional_count} PROVISIONAL
          </StatusBadge>
          <span>
            {data.summary.positive_count} positive ·{" "}
            {data.summary.negative_count} negative · {data.summary.zero_count}{" "}
            zero · {data.summary.insufficient_data_count} insufficient-data
            trips
          </span>
        </div>
        <div className="reporting-table-wrap">
          <table className="reporting-table">
            <caption>
              Lifecycle subtotals — cancelled-trip costs are included unless
              filtered out
            </caption>
            <thead>
              <tr>
                <th>Lifecycle</th>
                <th>Trips</th>
                <th>Revenue</th>
                <th>Direct cost</th>
                <th>Contribution</th>
              </tr>
            </thead>
            <tbody>
              {data.lifecycle_totals.map((row) => (
                <tr key={row.lifecycle}>
                  <td>{human(row.lifecycle)}</td>
                  <td>{row.trip_count}</td>
                  <td>{php(row.revenue)}</td>
                  <td>{php(row.direct_cost)}</td>
                  <td>{php(row.contribution)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <AdvanceSummary values={data.advance_summary} />
      </>
    );
  if (name === "trip-contribution")
    return (
      <div className="reporting-table-wrap">
        <table className="reporting-table">
          <caption>
            Current effective reviewed values of the selected trips
          </caption>
          <thead>
            <tr>
              {[
                "Trip / source records",
                "Customer / vehicle",
                "Lifecycle / review",
                "Revenue",
                "Direct cost",
                "Contribution",
                "Margin",
                "Input quality",
              ].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data.items as Trip[]).map((t) => (
              <tr key={t.id}>
                <td>
                  <Link href={t.review_href}>{t.trip_number}</Link>
                  <small>
                    {new Intl.DateTimeFormat("en", {
                      timeZone: data.scope.timezone,
                      dateStyle: "medium",
                    }).format(new Date(t.scheduled_pickup_at))}
                  </small>
                  <details>
                    <summary>Category costs</summary>
                    {t.category_costs.map((c) => (
                      <p key={c.category}>
                        {human(c.category)}: {php(c.reviewed_total)}
                      </p>
                    ))}
                    <p>Submitted revenue: {php(t.submitted_revenue)}</p>
                    <p>Submitted direct cost: {php(t.submitted_direct_cost)}</p>
                  </details>
                </td>
                <td>
                  {t.customer_name}
                  <small>{t.vehicle_name ?? "Unassigned vehicle"}</small>
                </td>
                <td>
                  {human(t.current_status)}
                  <small>
                    <StatusBadge
                      tone={t.status === "FINAL" ? "positive" : "warning"}
                    >
                      {t.status}
                    </StatusBadge>
                  </small>
                </td>
                <td>{php(t.revenue)}</td>
                <td>{php(t.direct_cost)}</td>
                <td
                  className={
                    t.contribution.startsWith("-") ? "reporting-negative" : ""
                  }
                >
                  {php(t.contribution)}
                </td>
                <td>{margin(t.margin_percent)}</td>
                <td>
                  {t.data_warnings.length
                    ? t.data_warnings.join(" ")
                    : "Reviewed inputs present"}
                  <details>
                    <summary>Review blockers</summary>
                    <p>{t.financial_review_status}</p>
                    {t.financial_review_blockers.map((b) => (
                      <p key={b}>{b}</p>
                    ))}
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  if (name === "customer-contribution")
    return (
      <div className="reporting-table-wrap">
        <table className="reporting-table">
          <caption>
            Customer contribution for the selected period — not an overall
            customer rating
          </caption>
          <thead>
            <tr>
              {[
                "Customer",
                "Trips",
                "Revenue",
                "Direct cost",
                "Contribution",
                "Weighted margin",
                "Negative trips",
                "Provisional exposure",
              ].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data.items as Customer[]).map((c) => (
              <tr key={c.customer_id}>
                <td>
                  <Link href={c.href}>{c.customer_name}</Link>
                </td>
                <td>{c.trip_count}</td>
                <td>{php(c.revenue)}</td>
                <td>{php(c.direct_cost)}</td>
                <td>{php(c.contribution)}</td>
                <td>{margin(c.weighted_margin_percent)}</td>
                <td>{c.negative_count}</td>
                <td>
                  {c.provisional_count} trips
                  <small>{php(c.provisional_contribution)} contribution</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  if (name === "direct-costs")
    return (
      <>
        <CostBreakdown categories={data.items as Category[]} query={query} />
        <div className="reporting-table-wrap">
          <table className="reporting-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Reviewed direct cost</th>
                <th>Submitted, including reviewed</th>
                <th>Unreviewed records</th>
              </tr>
            </thead>
            <tbody>
              {(data.items as Category[]).map((c) => (
                <tr key={c.category}>
                  <td>{human(c.category)}</td>
                  <td>{php(c.reviewed_total)}</td>
                  <td>{php(c.submitted_total)}</td>
                  <td>{c.unreviewed_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="panel-note">
          Captured advances of{" "}
          {php(String(data.advance_summary.captured_amount))} and confirmed
          issuance of {php(String(data.advance_summary.issued))} are shown
          separately. Neither is added as a second direct cost.
        </p>
      </>
    );
  return (
    <>
      <AdvanceSummary values={data.advance_summary} />
      <p className="panel-note">
        CAPTURE is an expense-category record. ISSUANCE is a separate confirmed
        funding record. Never add both as expenses or infer a settlement balance
        from a capture.
      </p>
      <div className="reporting-table-wrap">
        <table className="reporting-table">
          <thead>
            <tr>
              {[
                "Record type / ID",
                "Trip / history",
                "Captured amount",
                "Confirmed issued",
                "Applied",
                "Returned",
                "Outstanding",
                "Status",
              ].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data.items as Advance[]).map((a) => (
              <tr key={`${a.record_kind}:${a.id}`}>
                <td>
                  <strong>{a.record_kind}</strong>
                  <small>{a.id}</small>
                </td>
                <td>
                  <Link
                    href={`/reports/trip-contribution?${reportQuery(query, { trip_id: a.trip_id })}`}
                  >
                    Review trip records
                  </Link>
                  <small>
                    {a.record_kind === "CAPTURE"
                      ? `Linked issuance: ${a.issuance_id ?? "None"}`
                      : `Source capture: ${a.source_expense_id ?? "Direct issuance"}`}
                  </small>
                </td>
                <td>
                  {a.record_kind === "CAPTURE" ? php(a.amount ?? "0") : "N/A"}
                </td>
                <td>
                  {a.record_kind === "ISSUANCE"
                    ? php(a.amount_issued ?? "0")
                    : "Not established by capture"}
                </td>
                <td>{a.applied === undefined ? "N/A" : php(a.applied)}</td>
                <td>{a.returned === undefined ? "N/A" : php(a.returned)}</td>
                <td>
                  {a.outstanding === undefined
                    ? "Not inferred"
                    : php(a.outstanding)}
                </td>
                <td>
                  {a.record_kind === "CAPTURE" && a.unreconciled
                    ? "UNRECONCILED CAPTURE"
                    : a.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
export function AdvanceSummary({
  values,
}: {
  values: Record<string, string | number>;
}) {
  return (
    <dl className="master-fields reporting-advance-summary">
      {[
        ["Captured advance records", "captured_amount"],
        ["Confirmed active issuance", "issued"],
        ["Reviewed expenses applied", "applied"],
        ["Cash returned", "returned"],
        ["Confirmed outstanding", "outstanding"],
      ].map(([label, key]) => (
        <div key={key}>
          <dt>{label}</dt>
          <dd>{php(String(values[key] ?? "0"))}</dd>
        </div>
      ))}
      <div>
        <dt>Unreconciled captures</dt>
        <dd>{values.unreconciled_capture_count}</dd>
      </div>
    </dl>
  );
}
