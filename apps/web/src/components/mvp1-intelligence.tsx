"use client";
import "@/app/reporting.css";
import { FinancialPanel } from "./financials";
import type { Trip } from "@/lib/reporting";
import type { TripRecord } from "@/lib/trips";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrainCircuit, Download, Printer, RefreshCw } from "lucide-react";
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
import {
  REPORTS,
  canReport,
  periodToday,
  reportQuery,
  type ReportData,
  type ReportName,
} from "@/lib/reporting";
import {
  ContributionMetrics,
  FindingCards,
  CostBreakdown,
  CustomerCards,
  ReportTable,
} from "./reporting-views";

export function ReportingWorkspace({
  identity,
  mode = "report",
  reportName = "executive-contribution",
  initialFilters = {},
}: {
  identity: Identity;
  mode?: "dashboard" | "intelligence" | "report";
  reportName?: ReportName;
  initialFilters?: Record<string, string>;
}) {
  const today = periodToday(identity.organization.timezone);
  const defaults = {
    date_from: today.slice(0, 8) + "01",
    date_to: today,
    dataset: "business",
    ...initialFilters,
  };
  const [draft, setDraft] = useState<Record<string, string>>(defaults);
  const [filters, setFilters] = useState<Record<string, string>>(defaults);
  const [offset, setOffset] = useState(0),
    [refresh, setRefresh] = useState(0);
  const [snapshot, setSnapshot] = useState<{
    key: string;
    data?: ReportData;
    error?: string;
  }>();
  const [exportError, setExportError] = useState(""),
    [downloading, setDownloading] = useState(false);
  const pathname = usePathname(),
    allowed = canReport(identity);
  const selectedReport =
    mode === "intelligence" ? "financial-exceptions" : reportName;
  const query = reportQuery(filters, { offset: String(offset), limit: "50" });
  const requestKey = [
    identity.organization.id,
    mode,
    selectedReport,
    query,
    refresh,
  ].join("|");
  const data = snapshot?.key === requestKey ? snapshot.data : undefined;
  const error = snapshot?.key === requestKey ? (snapshot.error ?? "") : "";
  const loading = allowed && snapshot?.key !== requestKey;
  useEffect(() => {
    if (!allowed) return;
    const controller = new AbortController();
    const endpoint =
      mode === "dashboard"
        ? "/intelligence/overview"
        : `/reports/${selectedReport}`;
    fetch(`/api/v1${endpoint}?${query}`, {
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 401) {
          window.location.assign("/login?expired=1");
          throw new Error("Your session expired. Sign in again.");
        }
        const payload = await response.json();
        if (!response.ok)
          throw new Error(
            payload?.error?.message ??
              "Reporting is unavailable. No zero totals have been substituted.",
          );
        return payload as ReportData;
      })
      .then((payload) => {
        if (!controller.signal.aborted)
          setSnapshot({ key: requestKey, data: payload });
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setSnapshot({
            key: requestKey,
            error:
              e instanceof Error
                ? e.message
                : "Unable to calculate this report.",
          });
      });
    return () => controller.abort();
  }, [allowed, mode, selectedReport, query, requestKey]);
  if (!allowed)
    return (
      <>
        <PageHeader
          title="Financial reporting access"
          description="Owner intelligence requires complete financial permissions."
        />
        <ErrorState message="Your current permissions do not permit complete revenue, expense, fuel, advance and financial-review reporting. Costs or settlement balances will not be replaced by zero." />
      </>
    );
  function apply(next: Record<string, string>) {
    setDraft(next);
    setFilters(next);
    setOffset(0);
    window.history.replaceState(null, "", `${pathname}?${reportQuery(next)}`);
  }
  async function download() {
    setDownloading(true);
    setExportError("");
    try {
      const response = await fetch(
        `/api/v1/reports/${selectedReport}?${reportQuery(filters, { format: "csv" })}`,
        { cache: "no-store", credentials: "same-origin" },
      );
      if (response.status === 401) {
        window.location.assign("/login?expired=1");
        throw new Error("Sign in to export.");
      }
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body?.error?.message ?? "Export unavailable.");
      }
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `fleetpilot-${selectedReport}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed.");
    } finally {
      setDownloading(false);
    }
  }
  const title =
    mode === "dashboard"
      ? "Owner Dashboard"
      : mode === "intelligence"
        ? "Owner Intelligence"
        : (REPORTS.find(([key]) => key === reportName)?.[1] ?? "Reports");
  const description =
    mode === "dashboard"
      ? "Reviewed contribution, financial priorities, and the records behind them."
      : mode === "intelligence"
        ? "Explainable financial signals. Review the evidence before acting."
        : (REPORTS.find(([key]) => key === reportName)?.[2] ??
          "Contribution reporting");
  return (
    <div className="reporting-workspace page-stack">
      <PageHeader title={title} description={description}>
        <StatusBadge>Reviewed operational basis</StatusBadge>
      </PageHeader>
      {filters.dataset === "synthetic" && (
        <div className="reporting-demo-banner" role="note">
          <strong>SYNTHETIC VALIDATION DATA</strong>
          <span>
            Demonstration only. September 21–24, 2026 examples follow their
            scheduled pickup dates; they are not verified deliveries completed
            today.
          </span>
        </div>
      )}
      <Card className="reporting-filter-card">
        <form
          className="reporting-filters"
          onSubmit={(e) => {
            e.preventDefault();
            apply(draft);
          }}
        >
          <label>
            From
            <input
              type="date"
              value={draft.date_from ?? ""}
              required
              onChange={(e) =>
                setDraft({ ...draft, date_from: e.target.value })
              }
            />
          </label>
          <label>
            Through
            <input
              type="date"
              value={draft.date_to ?? ""}
              required
              onChange={(e) => setDraft({ ...draft, date_to: e.target.value })}
            />
          </label>
          <label>
            Lifecycle
            <select
              value={draft.lifecycle ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, lifecycle: e.target.value })
              }
            >
              <option value="">All, including cancelled</option>
              {[
                "SCHEDULED",
                "DISPATCHED",
                "PICKUP",
                "LOADED",
                "IN_TRANSIT",
                "DELIVERED",
                "COMPLETED",
                "CANCELLED",
              ].map((s) => (
                <option key={s} value={s}>
                  {s.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <label>
            Financial status
            <select
              value={draft.financial_status ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, financial_status: e.target.value })
              }
            >
              <option value="">All financial statuses</option>
              <option>FINAL</option>
              <option>PROVISIONAL</option>
            </select>
          </label>
          <label>
            Customer
            <select
              value={draft.customer_id ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, customer_id: e.target.value, trip_id: "" })
              }
            >
              <option value="">All customers</option>
              {data?.filter_options.customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
              {draft.customer_id &&
                !data?.filter_options.customers.some(
                  (c) => c.id === draft.customer_id,
                ) && (
                  <option value={draft.customer_id}>Selected customer</option>
                )}
            </select>
          </label>
          <label>
            Vehicle
            <select
              value={draft.vehicle_id ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, vehicle_id: e.target.value, trip_id: "" })
              }
            >
              <option value="">All vehicles</option>
              {data?.filter_options.vehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
              {draft.vehicle_id &&
                !data?.filter_options.vehicles.some(
                  (v) => v.id === draft.vehicle_id,
                ) && <option value={draft.vehicle_id}>Selected vehicle</option>}
            </select>
          </label>
          <button className="button primary" type="submit" disabled={loading}>
            Apply filters
          </button>
        </form>
        <div className="reporting-filter-actions">
          <span className="small muted">
            Date basis: scheduled pickup · {identity.organization.timezone}
          </span>
          {data?.scope.demo_available && (
            <button
              type="button"
              className="button secondary"
              onClick={() =>
                apply({
                  date_from: "2026-09-21",
                  date_to: "2026-09-24",
                  dataset: "synthetic",
                })
              }
            >
              Demo: Sep 21–24, 2026
            </button>
          )}
          <button
            type="button"
            className="text-button"
            onClick={() =>
              apply({
                date_from: today.slice(0, 8) + "01",
                date_to: today,
                dataset: "business",
              })
            }
          >
            Business records / reset
          </button>
          {filters.trip_id && (
            <button
              className="text-button"
              onClick={() => apply({ ...filters, trip_id: "" })}
            >
              Clear selected trip
            </button>
          )}
        </div>
      </Card>
      <nav className="reporting-tabs" aria-label="Contribution reports">
        {REPORTS.map(([key, label]) => (
          <Link
            key={key}
            className={
              mode === "report" && selectedReport === key ? "active" : ""
            }
            href={`/reports/${key}?${reportQuery(filters)}`}
          >
            {label}
          </Link>
        ))}
      </nav>
      {loading && <LoadingState />}
      {error && (
        <>
          <ErrorState message={error} />
          <button
            className="button secondary"
            onClick={() => setRefresh((n) => n + 1)}
          >
            <RefreshCw size={16} />
            Retry report
          </button>
        </>
      )}
      {data && !loading && !error && (
        <>
          <div className="reporting-scope">
            <strong>{data.scope.organization_name}</strong>
            <span>
              {data.scope.date_from} through {data.scope.date_to} ·{" "}
              {data.scope.date_basis} · {data.scope.timezone}
            </span>
            <span>
              {data.scope.record_count} trips · {data.scope.lifecycle} ·{" "}
              {data.scope.financial_status}
            </span>
          </div>
          <p className="reporting-qualification">{data.scope.qualification}</p>
          <div className="reporting-toolbar">
            <button
              className="button secondary"
              onClick={download}
              disabled={downloading}
            >
              <Download size={16} />
              {downloading
                ? "Preparing complete CSV…"
                : "Export complete filtered CSV"}
            </button>
            <a
              className="button secondary"
              href={`/api/v1/reports/${selectedReport}?${reportQuery(filters, { format: "print" })}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Printer size={16} />
              Open print-ready report
            </a>
            <button
              className="text-button"
              onClick={() => setRefresh((n) => n + 1)}
            >
              <RefreshCw size={15} />
              Recalculate
            </button>
          </div>
          <p className="small muted">
            Exports are newly calculated with their own timestamp and
            fingerprint. Browser printing supports Save as PDF.
          </p>
          {exportError && <ErrorState message={exportError} />}
          {(mode === "dashboard" || mode === "intelligence") && (
            <ContributionMetrics value={data.summary} />
          )}
          {(mode === "dashboard" || mode === "intelligence") && (
            <Card
              title="Owner Intelligence Brief"
              className="reporting-owner-brief"
              action={<BrainCircuit size={22} />}
            >
              <div className="reporting-counts">
                <StatusBadge tone="warning">
                  {data.summary.provisional_count} PROVISIONAL
                </StatusBadge>
                <StatusBadge tone="positive">
                  {data.summary.final_count} FINAL
                </StatusBadge>
              </div>
              {data.owner_brief.map((p) => (
                <p key={p}>{p}</p>
              ))}
              <p className="small muted">
                Deterministic rules from authorized source records. No
                forecasts, fuel-theft conclusions, or autonomous financial
                approvals.
              </p>
            </Card>
          )}
          {mode === "dashboard" ? (
            <div className="reporting-dashboard-grid">
              <Card title="Priority Financial Exceptions">
                <FindingCards
                  findings={data.priority_findings.slice(0, 4)}
                  query={filters}
                />
                <Link href={`/intelligence?${reportQuery(filters)}`}>
                  View all {data.finding_count} findings
                </Link>
              </Card>
              <Card title="Direct Cost Breakdown">
                <CostBreakdown
                  categories={data.category_summary}
                  query={filters}
                />
              </Card>
              <Card title="Customer Contribution">
                <p className="small muted">
                  Contribution for the selected period · top five shown
                </p>
                <CustomerCards customers={data.top_customers} />
                <Link
                  href={`/reports/customer-contribution?${reportQuery(filters)}`}
                >
                  Open complete customer report
                </Link>
              </Card>
              <Card title="Recent Material Financial Changes">
                {!data.history_available ? (
                  <p>History is unavailable with your current permissions.</p>
                ) : data.recent_changes.length ? (
                  data.recent_changes.map((c) => (
                    <div key={c.id}>
                      <p>
                        {c.field_name}: {JSON.stringify(c.old_value)} →{" "}
                        {JSON.stringify(c.new_value)}
                      </p>
                      <small>{c.created_at}</small>
                      <p>
                        <Link
                          href={`/reports/trip-contribution?${reportQuery(filters, { trip_id: c.trip_id })}`}
                        >
                          Review affected trip
                        </Link>
                      </p>
                    </div>
                  ))
                ) : (
                  <EmptyState
                    title="No supported change history in this scope"
                    description="No before-and-after comparison or financial impact has been invented."
                  />
                )}
              </Card>
            </div>
          ) : (
            <Card className="reporting-main-report">
              <ReportTable name={selectedReport} data={data} query={filters} />
              <div className="reporting-pagination">
                <button
                  className="button secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset((n) => Math.max(0, n - 50))}
                >
                  Previous rows
                </button>
                <span>
                  {data.total === 0
                    ? "0"
                    : `${offset + 1}–${Math.min(offset + 50, data.total)}`}{" "}
                  of {data.total} rows · totals cover the complete cohort
                </span>
                <button
                  className="button secondary"
                  disabled={offset + 50 >= data.total}
                  onClick={() => setOffset((n) => n + 50)}
                >
                  Next rows
                </button>
              </div>
            </Card>
          )}
          {selectedReport === "trip-contribution" &&
            filters.trip_id &&
            data.items.length === 1 &&
            (() => {
              const selected = data.items[0] as Trip;
              return (
                <FinancialPanel
                  trip={{
                    id: selected.id,
                    version: selected.version,
                    current_status:
                      selected.current_status as TripRecord["current_status"],
                  }}
                  identity={identity}
                  revision={refresh}
                />
              );
            })()}
          <details className="reporting-audit">
            <summary>Scope, data quality and calculation evidence</summary>
            <p>
              Calculated: {data.scope.calculated_at} · Rule:{" "}
              {data.scope.rule_version}
            </p>
            <p className="reporting-fingerprint">
              Fingerprint: {data.scope.fingerprint}
            </p>
            {data.scope.warnings.map((w) => (
              <p key={w}>{w}</p>
            ))}
            <p>
              Customer: {data.scope.customer_id ?? "ALL"} · Vehicle:{" "}
              {data.scope.vehicle_id ?? "ALL"} · Trip:{" "}
              {data.scope.trip_id ?? "ALL"}
            </p>
          </details>
          {can(identity, "organization.manage") &&
            ["OWNER", "ADMIN"].includes(identity.membership.role) && (
              <PolicySettings
                policy={data.policy}
                onSaved={() => setRefresh((n) => n + 1)}
              />
            )}
        </>
      )}
    </div>
  );
}
function PolicySettings({
  policy,
  onSaved,
}: {
  policy: Record<string, string>;
  onSaved: () => void;
}) {
  const [values, setValues] = useState(policy),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  return (
    <details className="reporting-policy">
      <summary>Reporting policy — owner/admin settings</summary>
      <p>
        Configurable product defaults, not industry benchmarks. Changes are
        audited and do not approve or settle any trip.
      </p>
      <form
        className="reporting-filters"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          setNotice("");
          try {
            const r = await fetch("/api/v1/reports/policy", {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              credentials: "same-origin",
              body: JSON.stringify(values),
            });
            const b = await r.json();
            if (!r.ok)
              throw new Error(b?.error?.message ?? "Policy update failed.");
            setNotice("Policy saved with audit history.");
            onSaved();
          } catch (e) {
            setError(e instanceof Error ? e.message : "Unable to save policy.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {[
          ["low_margin_percent", "Low-margin threshold (%)"],
          ["direct_cost_pressure_percent", "Direct-cost pressure (%)"],
          ["cost_concentration_percent", "Cost concentration (%)"],
          ["material_change_php", "Material source change (PHP)"],
        ].map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              inputMode="decimal"
              value={values[key] ?? ""}
              required
              onChange={(e) => setValues({ ...values, [key]: e.target.value })}
            />
          </label>
        ))}
        <button className="button primary" disabled={busy} type="submit">
          Save audited policy
        </button>
      </form>
      {error && <ErrorState message={error} />}
      <p role="status">{notice}</p>
    </details>
  );
}
