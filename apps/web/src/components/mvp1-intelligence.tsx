"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Banknote,
  BrainCircuit,
  ChartNoAxesCombined,
  CircleDollarSign,
  ClipboardCheck,
  FileChartColumnIncreasing,
  Gauge,
  ReceiptText,
  Scale,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  UsersRound,
  WalletCards,
} from "lucide-react";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
} from "@fleetpilot/ui";
import { can } from "@fleetpilot/auth";
import type { Identity } from "@fleetpilot/types";
import { request } from "@/lib/client";
import { php } from "@/lib/money";
import { dateLabel, human } from "@/lib/trips";
import {
  buildExceptions,
  groupCustomers,
  groupDirectCosts,
  hasInsightAccess,
  isFinancialAudit,
  moneyCents,
  summarizeAdvances,
  summarizeContribution,
  type AuditEvent,
  type CashAdvance,
  type ContributionRow,
  type IntelligenceException,
} from "@/lib/mvp1-intelligence";

export type ReportKey =
  | "executive-contribution"
  | "trip-contribution"
  | "customer-contribution"
  | "direct-cost-analysis"
  | "financial-exceptions"
  | "cash-advance-settlement";

export const REPORTS: {
  key: ReportKey;
  title: string;
  description: string;
  icon: typeof ChartNoAxesCombined;
}[] = [
  {
    key: "executive-contribution",
    title: "Executive Contribution",
    description:
      "Reviewed revenue, direct cost, contribution, weighted margin and financial-review exposure.",
    icon: Gauge,
  },
  {
    key: "trip-contribution",
    title: "Trip Contribution",
    description:
      "Trace every contribution figure to the authoritative trip record.",
    icon: ChartNoAxesCombined,
  },
  {
    key: "customer-contribution",
    title: "Customer Contribution",
    description:
      "Group reviewed contribution by customer without converting it into net profit.",
    icon: UsersRound,
  },
  {
    key: "direct-cost-analysis",
    title: "Direct Cost Analysis",
    description:
      "See which reviewed expense categories consume the largest share of direct trip cost.",
    icon: ReceiptText,
  },
  {
    key: "financial-exceptions",
    title: "Financial Exceptions",
    description:
      "Loss trips, low margins, review blockers, missing revenue and cost concentration.",
    icon: AlertTriangle,
  },
  {
    key: "cash-advance-settlement",
    title: "Cash Advance & Settlement",
    description:
      "Issued, applied, returned and outstanding cash advances kept separate from direct cost.",
    icon: WalletCards,
  },
];

type ContributionResponse = { items: ContributionRow[]; total: number };
type AdvanceResponse = { items: CashAdvance[]; total: number };

async function loadContributionRows(): Promise<ContributionRow[]> {
  const all: ContributionRow[] = [];
  let offset = 0;
  let total = 0;
  do {
    const result = await request<ContributionResponse>(
      `/profitability/trips?limit=100&offset=${offset}&direction=desc`,
    );
    all.push(...result.items);
    total = result.total;
    offset += result.items.length;
    if (result.items.length === 0) break;
  } while (offset < total);
  return all;
}

async function loadCashAdvances(
  rows: ContributionRow[],
): Promise<CashAdvance[]> {
  const output: CashAdvance[] = [];
  for (const row of rows) {
    let offset = 0;
    let total = 0;
    do {
      const result = await request<AdvanceResponse>(
        `/trips/${row.trip_id}/cash-advances?limit=100&offset=${offset}`,
      );
      output.push(
        ...result.items.map((advance) => ({
          ...advance,
          trip_id: row.trip_id,
          trip_number: row.trip_number,
        })),
      );
      total = result.total;
      offset += result.items.length;
      if (result.items.length === 0) break;
    } while (offset < total);
  }
  return output;
}

function useMvp1Data(identity: Identity, includeAdvances = false) {
  const [rows, setRows] = useState<ContributionRow[]>();
  const [audits, setAudits] = useState<AuditEvent[]>([]);
  const [advances, setAdvances] = useState<CashAdvance[]>([]);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const access = hasInsightAccess(identity);

  useEffect(() => {
    let live = true;
    if (!access)
      return () => {
        live = false;
      };

    async function load() {
      try {
        const contributionRows = await loadContributionRows();
        const [auditRows, advanceRows] = await Promise.all([
          can(identity, "audit.read")
            ? request<AuditEvent[]>("/audit-logs?limit=50").catch(() => [])
            : Promise.resolve([]),
          includeAdvances
            ? loadCashAdvances(contributionRows)
            : Promise.resolve([]),
        ]);
        if (!live) return;
        setRows(contributionRows);
        setAudits(auditRows.filter(isFinancialAudit));
        setAdvances(advanceRows);
        setError("");
      } catch (caught) {
        if (live)
          setError(
            caught instanceof Error
              ? caught.message
              : "Unable to load owner intelligence.",
          );
      }
    }
    void load();
    return () => {
      live = false;
    };
  }, [access, identity, includeAdvances, revision]);

  return {
    access,
    rows,
    audits,
    advances,
    error,
    reload: () => setRevision((value) => value + 1),
  };
}

function InsightKpi({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ReactNode;
  tone?: "neutral" | "positive" | "active" | "warning" | "critical";
}) {
  return (
    <Card className={`insight-kpi insight-kpi-${tone}`}>
      <div className="insight-kpi-top">
        <span className={`icon-box icon-box-${tone}`}>{icon}</span>
        <span>{label}</span>
      </div>
      <strong className="insight-kpi-value">{value}</strong>
      <span className="small muted">{hint}</span>
    </Card>
  );
}

function AccessBoundary({
  access,
  rows,
  error,
  reload,
  children,
}: {
  access: boolean;
  rows: ContributionRow[] | undefined;
  error: string;
  reload: () => void;
  children: React.ReactNode;
}) {
  if (!access) {
    return (
      <ErrorState message="This role does not have the existing financial permissions required for owner Intelligence and Reports." />
    );
  }
  if (error) {
    return (
      <div className="page-stack">
        <ErrorState message={error} />
        <button className="button secondary" onClick={reload}>
          Retry owner intelligence
        </button>
      </div>
    );
  }
  if (!rows) return <LoadingState />;
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={<ChartNoAxesCombined size={22} />}
        title="No contribution records yet"
        description="Reviewed revenue and direct-cost records will appear here when authorized trip financials are available."
      />
    );
  }
  return <>{children}</>;
}
function SummaryKpis({ rows }: { rows: ContributionRow[] }) {
  const summary = summarizeContribution(rows);
  return (
    <div className="insight-kpi-grid">
      <InsightKpi
        label="Reviewed Revenue"
        value={php(summary.revenue)}
        hint="Reviewed effective operational revenue"
        icon={<CircleDollarSign />}
        tone="positive"
      />
      <InsightKpi
        label="Direct Cost"
        value={php(summary.directCost)}
        hint="Reviewed direct trip cost only"
        icon={<ReceiptText />}
        tone="warning"
      />
      <InsightKpi
        label="Contribution"
        value={php(summary.contribution)}
        hint="Revenue minus reviewed direct trip cost"
        icon={<Scale />}
        tone={moneyCents(summary.contribution) < 0n ? "critical" : "active"}
      />
      <InsightKpi
        label="Weighted Margin"
        value={
          summary.weightedMargin === null ? "N/A" : `${summary.weightedMargin}%`
        }
        hint="Aggregate contribution ÷ reviewed revenue"
        icon={<Gauge />}
        tone="active"
      />
      <InsightKpi
        label="Loss-Making Trips"
        value={String(summary.lossTrips)}
        hint="Trips with negative reviewed contribution"
        icon={<TrendingDown />}
        tone={summary.lossTrips ? "critical" : "positive"}
      />
      <InsightKpi
        label="Needs Financial Review"
        value={String(summary.needsReview)}
        hint="Completed trips that are not FINAL"
        icon={<ClipboardCheck />}
        tone={summary.needsReview ? "warning" : "positive"}
      />
    </div>
  );
}

function ScopeLine({ rows }: { rows: ContributionRow[] }) {
  const finalCount = rows.filter((row) => row.status === "FINAL").length;
  return (
    <div className="report-scope">
      <span>
        <ShieldCheck size={15} /> Basis: REVIEWED_EFFECTIVE
      </span>
      <span>
        {rows.length} authorized trip{rows.length === 1 ? "" : "s"}
      </span>
      <span>
        {finalCount} FINAL · {rows.length - finalCount} PROVISIONAL
      </span>
      <span>Currency: PHP</span>
    </div>
  );
}

function ExceptionCards({
  exceptions,
  limit,
}: {
  exceptions: IntelligenceException[];
  limit?: number;
}) {
  const visible =
    typeof limit === "number" ? exceptions.slice(0, limit) : exceptions;
  if (!visible.length) {
    return (
      <EmptyState
        title="No exception signals"
        description="The current authorized contribution records do not trigger the locked MVP1 exception rules."
      />
    );
  }
  return (
    <div className="exception-list">
      {visible.map((item) => (
        <article
          className={`exception-row exception-${item.tone}`}
          key={item.key}
        >
          <div className="exception-marker" aria-hidden="true" />
          <div>
            <div className="exception-meta">
              <span>OBSERVATION · {human(item.kind)}</span>
              <StatusBadge
                tone={item.tone === "critical" ? "warning" : item.tone}
              >
                {item.trip.status}
              </StatusBadge>
            </div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
            <div className="exception-recommendation">
              <span>RECOMMENDED REVIEW</span>
              <p>{item.recommendation}</p>
            </div>
            <Link href={`/trips/${item.trip.trip_id}`}>Open source trip →</Link>
          </div>
        </article>
      ))}
    </div>
  );
}

function CostTable({
  rows,
  limit,
}: {
  rows: ContributionRow[];
  limit?: number;
}) {
  const costs = groupDirectCosts(rows);
  const visible = typeof limit === "number" ? costs.slice(0, limit) : costs;
  if (!visible.length)
    return <p className="muted">No reviewed direct-cost categories.</p>;
  return (
    <div className="rank-list">
      {visible.map((item, index) => (
        <div className="rank-row" key={item.category}>
          <span className="rank-number">
            {String(index + 1).padStart(2, "0")}
          </span>
          <div>
            <strong>{human(item.category)}</strong>
            <small>{item.share ?? "N/A"}% of reviewed direct trip cost</small>
          </div>
          <strong>{php(item.reviewedTotal)}</strong>
        </div>
      ))}
    </div>
  );
}
function CustomerTable({
  rows,
  limit,
}: {
  rows: ContributionRow[];
  limit?: number;
}) {
  const customers = groupCustomers(rows);
  const visible =
    typeof limit === "number" ? customers.slice(0, limit) : customers;
  if (!visible.length)
    return <p className="muted">No customer contribution records.</p>;
  return (
    <div className="table-scroll">
      <table className="report-table">
        <thead>
          <tr>
            <th>Customer</th>
            <th>Trips</th>
            <th>Reviewed revenue</th>
            <th>Direct cost</th>
            <th>Contribution</th>
            <th>Margin</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row) => (
            <tr key={row.customer}>
              <td>
                <strong>{row.customer}</strong>
              </td>
              <td>{row.trips}</td>
              <td>{php(row.revenue)}</td>
              <td>{php(row.directCost)}</td>
              <td>{php(row.contribution)}</td>
              <td>{row.margin === null ? "N/A" : `${row.margin}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecentChanges({ audits }: { audits: AuditEvent[] }) {
  if (!audits.length) {
    return (
      <p className="muted">
        No authorized financial audit events are available to this view.
      </p>
    );
  }
  return (
    <div className="change-list">
      {audits.slice(0, 6).map((event) => (
        <div className="change-row" key={event.id}>
          <span className="change-dot" />
          <div>
            <strong>{event.action.split(".").map(human).join(" · ")}</strong>
            <small>
              {event.entity_type} · {dateLabel(event.created_at)}
            </small>
          </div>
        </div>
      ))}
    </div>
  );
}
export function Mvp1Dashboard({ identity }: { identity: Identity }) {
  const data = useMvp1Data(identity);
  const rows = useMemo(() => data.rows ?? [], [data.rows]);
  const exceptions = useMemo(() => buildExceptions(rows), [rows]);
  const customers = useMemo(() => groupCustomers(rows), [rows]);
  return (
    <AccessBoundary {...data}>
      <ScopeLine rows={rows} />
      <SummaryKpis rows={rows} />
      <div className="decision-grid">
        <Card
          title="Intelligence Brief"
          className="decision-card"
          action={<Link href="/intelligence">Open Intelligence →</Link>}
        >
          <div className="brief-lead">
            <Sparkles size={20} />
            <p>
              <strong>{exceptions.length}</strong> explainable exception signal
              {exceptions.length === 1 ? "" : "s"} across{" "}
              <strong>{rows.length}</strong> authorized trips.
            </p>
          </div>
          <ExceptionCards exceptions={exceptions} limit={3} />
        </Card>
        <Card
          title="Cost Leakage Watch"
          className="decision-card"
          action={
            <Link href="/reports/direct-cost-analysis">Open report →</Link>
          }
        >
          <p className="small muted decision-note">
            Concentration signal only; this is not a fraud finding.
          </p>
          <CostTable rows={rows} limit={4} />
        </Card>
        <Card
          title="Worst Exceptions"
          className="decision-card"
          action={
            <Link href="/reports/financial-exceptions">All exceptions →</Link>
          }
        >
          <ExceptionCards
            exceptions={exceptions.filter((item) => item.tone !== "active")}
            limit={4}
          />
        </Card>
        <Card
          title="Top Contribution Customers"
          className="decision-card"
          action={
            <Link href="/reports/customer-contribution">Open report →</Link>
          }
        >
          {customers.slice(0, 5).map((row) => (
            <div className="customer-compact" key={row.customer}>
              <span>
                <strong>{row.customer}</strong>
                <small>
                  {row.trips} trip{row.trips === 1 ? "" : "s"} ·{" "}
                  {row.margin ?? "N/A"}% margin
                </small>
              </span>
              <strong>{php(row.contribution)}</strong>
            </div>
          ))}
        </Card>
        <Card
          title="Recent Financial Changes"
          className="decision-card"
          action={
            can(identity, "audit.read") ? (
              <span className="small muted">Audit-backed</span>
            ) : undefined
          }
        >
          <RecentChanges audits={data.audits} />
        </Card>
        <Card
          title="Owner Decision Support"
          className="decision-card decision-guide"
        >
          <BrainCircuit size={24} />
          <p>
            Use Intelligence to identify the exception, then open the source
            trip before changing an operational or financial record.
          </p>
          <div>
            <Link className="button primary" href="/intelligence">
              Review Intelligence
            </Link>
            <Link className="button secondary" href="/reports">
              Open six Reports
            </Link>
          </div>
        </Card>
      </div>
    </AccessBoundary>
  );
}
export function Mvp1Intelligence({ identity }: { identity: Identity }) {
  const data = useMvp1Data(identity);
  const rows = useMemo(() => data.rows ?? [], [data.rows]);
  const exceptions = useMemo(() => buildExceptions(rows), [rows]);
  const summary = useMemo(() => summarizeContribution(rows), [rows]);
  return (
    <div className="master-page intelligence-page">
      <PageHeader
        title="FleetPilot Intelligence"
        description="Explainable owner brief from authorized records: observation → evidence → recommended review."
      >
        <StatusBadge
          tone={
            exceptions.some((item) => item.tone === "critical")
              ? "warning"
              : "positive"
          }
        >
          {identity.organization.slug === "demo-logistics"
            ? "Demo workspace"
            : "Owner intelligence"}
        </StatusBadge>
      </PageHeader>
      <AccessBoundary {...data}>
        <ScopeLine rows={rows} />
        <Card className="intelligence-hero">
          <div className="intelligence-hero-icon">
            <BrainCircuit size={28} />
          </div>
          <div>
            <span className="eyebrow">OWNER BRIEF</span>
            <h2>
              {exceptions.length
                ? `${exceptions.length} item${exceptions.length === 1 ? "" : "s"} deserve review`
                : "No current exception signals"}
            </h2>
            <p>
              Reviewed contribution is{" "}
              <strong>{php(summary.contribution)}</strong> on{" "}
              <strong>{php(summary.revenue)}</strong> reviewed revenue. This is
              contribution, not net profit.
            </p>
          </div>
          <Link
            className="button secondary"
            href="/reports/executive-contribution"
          >
            Executive report
          </Link>
        </Card>
        <div className="intelligence-grid">
          <Card title="Priority Exceptions" className="intelligence-main">
            <ExceptionCards exceptions={exceptions} />
          </Card>
          <div className="intelligence-side">
            <Card title="Cost Concentration">
              <CostTable rows={rows} limit={5} />
            </Card>
            <Card title="Top Contribution Customers">
              <CustomerTable rows={rows} limit={5} />
            </Card>
            <Card title="Recent Financial Changes">
              <RecentChanges audits={data.audits} />
            </Card>
          </div>
        </div>
        <Card title="Evidence Standard" className="evidence-standard">
          <ShieldCheck size={22} />
          <p>
            Every amount on this page comes from the existing authorized
            profitability response. FleetPilot Intelligence does not replace
            trip financial review, approval, audit history, or the server
            calculation layer.
          </p>
        </Card>
      </AccessBoundary>
    </div>
  );
}
export function Mvp1ReportsIndex({ identity }: { identity: Identity }) {
  const access = hasInsightAccess(identity);
  return (
    <div className="master-page reports-index">
      <PageHeader
        title="Reports"
        description="Six contribution-based reports using the same verified owner financial basis."
      >
        <StatusBadge tone="active">6 reports</StatusBadge>
      </PageHeader>
      {!access ? (
        <ErrorState message="This role does not have the existing financial permissions required for these reports." />
      ) : (
        <>
          <div className="report-index-grid">
            {REPORTS.map(({ key, title, description, icon: Icon }) => (
              <Link
                href={`/reports/${key}`}
                className="report-index-card"
                key={key}
              >
                <span className="report-index-icon">
                  <Icon size={22} />
                </span>
                <span>
                  <strong>{title}</strong>
                  <small>{description}</small>
                </span>
                <span aria-hidden="true">→</span>
              </Link>
            ))}
          </div>
          <Card className="report-governance-note">
            <ShieldCheck size={20} />
            <p>
              <strong>Reporting guardrail:</strong> these views group and sum
              server-calculated reviewed effective values. They do not rewrite
              the trip profitability formula, financial-finalization policy,
              permissions, or tenant isolation.
            </p>
          </Card>
        </>
      )}
    </div>
  );
}

function TripContributionTable({ rows }: { rows: ContributionRow[] }) {
  return (
    <div className="table-scroll">
      <table className="report-table">
        <thead>
          <tr>
            <th>Trip</th>
            <th>Customer</th>
            <th>Reviewed revenue</th>
            <th>Direct cost</th>
            <th>Contribution</th>
            <th>Margin</th>
            <th>Financial state</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.trip_id}>
              <td>
                <Link href={`/trips/${row.trip_id}`}>
                  <strong>{row.trip_number}</strong>
                </Link>
              </td>
              <td>{row.customer_name}</td>
              <td>{php(row.revenue.effective_total)}</td>
              <td>{php(row.direct_cost.effective_total)}</td>
              <td>{php(row.contribution_amount)}</td>
              <td>
                {row.contribution_margin_percent === null
                  ? "N/A"
                  : `${row.contribution_margin_percent}%`}
              </td>
              <td>
                <StatusBadge
                  tone={row.status === "FINAL" ? "positive" : "warning"}
                >
                  {row.status}
                </StatusBadge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function DirectCostReport({ rows }: { rows: ContributionRow[] }) {
  const costs = groupDirectCosts(rows);
  return (
    <div className="table-scroll">
      <table className="report-table">
        <thead>
          <tr>
            <th>Direct-cost category</th>
            <th>Reviewed total</th>
            <th>Share of direct cost</th>
            <th>Signal</th>
          </tr>
        </thead>
        <tbody>
          {costs.map((row) => (
            <tr key={row.category}>
              <td>
                <strong>{human(row.category)}</strong>
              </td>
              <td>{php(row.reviewedTotal)}</td>
              <td>{row.share === null ? "N/A" : `${row.share}%`}</td>
              <td>
                {row.share !== null && Number(row.share) >= 50 ? (
                  <StatusBadge tone="warning">Concentrated</StatusBadge>
                ) : (
                  <StatusBadge>Monitor</StatusBadge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CashAdvanceReport({ advances }: { advances: CashAdvance[] }) {
  const summary = summarizeAdvances(advances);
  return (
    <>
      <div className="insight-kpi-grid insight-kpi-grid-five">
        <InsightKpi
          label="Advances Issued"
          value={php(summary.issued)}
          hint="Cash issued; not an added trip cost"
          icon={<Banknote />}
          tone="active"
        />
        <InsightKpi
          label="Expenses Applied"
          value={php(summary.applied)}
          hint="Settlement against recorded expenses"
          icon={<ReceiptText />}
          tone="positive"
        />
        <InsightKpi
          label="Cash Returned"
          value={php(summary.returned)}
          hint="Returned settlement cash"
          icon={<Banknote />}
          tone="neutral"
        />
        <InsightKpi
          label="Outstanding"
          value={php(summary.outstanding)}
          hint="Unsettled advance balance"
          icon={<WalletCards />}
          tone={moneyCents(summary.outstanding) > 0n ? "warning" : "positive"}
        />
        <InsightKpi
          label="Unsettled Advances"
          value={String(summary.unsettled)}
          hint="Issued or partially settled"
          icon={<ClipboardCheck />}
          tone={summary.unsettled ? "warning" : "positive"}
        />
      </div>
      {advances.length ? (
        <div className="table-scroll">
          <table className="report-table">
            <thead>
              <tr>
                <th>Trip</th>
                <th>Issued</th>
                <th>Applied</th>
                <th>Returned</th>
                <th>Outstanding</th>
                <th>Status</th>
                <th>Issued at</th>
              </tr>
            </thead>
            <tbody>
              {advances.map((item) => (
                <tr key={item.id}>
                  <td>
                    <Link href={`/trips/${item.trip_id}`}>
                      <strong>{item.trip_number}</strong>
                    </Link>
                  </td>
                  <td>{php(item.amount_issued)}</td>
                  <td>{php(item.applied)}</td>
                  <td>{php(item.returned)}</td>
                  <td>{php(item.outstanding)}</td>
                  <td>
                    <StatusBadge
                      tone={
                        item.status === "SETTLED"
                          ? "positive"
                          : item.status === "VOIDED"
                            ? "neutral"
                            : "warning"
                      }
                    >
                      {human(item.status)}
                    </StatusBadge>
                  </td>
                  <td>{dateLabel(item.issued_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No cash advances"
          description="No authorized cash-advance records were returned for the current trip set."
        />
      )}
    </>
  );
}
export function Mvp1Report({
  identity,
  report,
}: {
  identity: Identity;
  report: ReportKey;
}) {
  const meta = REPORTS.find((item) => item.key === report)!;
  const data = useMvp1Data(identity, report === "cash-advance-settlement");
  const rows = useMemo(() => data.rows ?? [], [data.rows]);
  const exceptions = useMemo(() => buildExceptions(rows), [rows]);
  return (
    <div className="master-page report-page">
      <PageHeader title={meta.title} description={meta.description}>
        <Link className="button secondary" href="/reports">
          All Reports
        </Link>
      </PageHeader>
      <AccessBoundary {...data}>
        <ScopeLine rows={rows} />
        {report === "executive-contribution" && (
          <>
            <SummaryKpis rows={rows} />
            <div className="report-two-column">
              <Card title="Customer Contribution">
                <CustomerTable rows={rows} limit={8} />
              </Card>
              <Card title="Highest-Priority Exceptions">
                <ExceptionCards exceptions={exceptions} limit={6} />
              </Card>
            </div>
          </>
        )}
        {report === "trip-contribution" && (
          <Card title="Trip Contribution Ledger">
            <TripContributionTable rows={rows} />
          </Card>
        )}
        {report === "customer-contribution" && (
          <Card title="Customer Contribution">
            <CustomerTable rows={rows} />
          </Card>
        )}
        {report === "direct-cost-analysis" && (
          <Card title="Reviewed Direct Cost by Category">
            <DirectCostReport rows={rows} />
          </Card>
        )}
        {report === "financial-exceptions" && (
          <Card title="Explainable Financial Exceptions">
            <ExceptionCards exceptions={exceptions} />
          </Card>
        )}
        {report === "cash-advance-settlement" && (
          <Card title="Cash Advance & Settlement">
            <CashAdvanceReport advances={data.advances} />
          </Card>
        )}
        <Card className="report-source-note">
          <FileChartColumnIncreasing size={20} />
          <p>
            <strong>Source traceability:</strong> open a trip from this report
            to inspect its reviewed revenue, direct-cost records, cash advances,
            corrections, review state and audit-backed history.
          </p>
        </Card>
      </AccessBoundary>
    </div>
  );
}
