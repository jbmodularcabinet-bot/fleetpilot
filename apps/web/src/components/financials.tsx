"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Card,
  ErrorState,
  LoadingState,
  EmptyState,
  PageHeader,
} from "@fleetpilot/ui";
import { can } from "@fleetpilot/auth";
import type { Identity } from "@fleetpilot/types";
import { request } from "@/lib/client";
import { php, validDecimal } from "@/lib/money";
import { dateLabel, human, tripStatuses, type TripRecord } from "@/lib/trips";
import { GovernancePanel } from "./governance";
import { validReason, adjustmentValue } from "./adjustments";

export type Financial = {
  trip_id: string;
  currency: string;
  status: string;
  unreviewed_count: number;
  financial_review_status?: string;
  revenue: {
    effective_total: string;
    submitted_total: string;
    breakdown: Breakdown[];
  };
  direct_cost: {
    effective_total: string;
    submitted_total: string;
    breakdown: Breakdown[];
  };
  contribution_amount: string;
  contribution_margin_percent: string | null;
  excluded_cash_advances: string;
};
type Breakdown = {
  category: string;
  submitted_total: string;
  reviewed_total: string;
};
type Revenue = {
  id: string;
  revenue_type: string;
  amount: string;
  effective_amount: string;
  status: string;
  sequence: number;
  administratively_voided: boolean;
  created_by: string;
  created_at: string;
  reviewed_at: string | null;
  effective_description: string | null;
  effective_reference_number: string | null;
  history?: History[];
};
type History = {
  id: string;
  field_name: string;
  old_value: string | boolean | null;
  new_value: string | boolean | null;
  reason: string;
  created_at: string;
  created_by: string;
  adjustment_status: string;
};
const kinds = [
  "BASE_TRIP_CHARGE",
  "SURCHARGE",
  "WAITING_TIME",
  "SPECIAL_HANDLING",
  "OTHER",
];
export function FinancialSummary({ value }: { value: Financial }) {
  return (
    <>
      <p className="small">
        <strong>{value.status}</strong> · Reviewed effective values · PHP ·
        Operational charges, not cash collected or net profit.
      </p>
      {value.financial_review_status && (
        <p className="small">
          Financial review: {human(value.financial_review_status)}
        </p>
      )}
      <dl className="master-fields">
        <div>
          <dt>Revenue</dt>
          <dd>{php(value.revenue.effective_total)}</dd>
        </div>
        <div>
          <dt>Direct trip cost</dt>
          <dd>{php(value.direct_cost.effective_total)}</dd>
        </div>
        <div>
          <dt>Contribution</dt>
          <dd>{php(value.contribution_amount)}</dd>
        </div>
        <div>
          <dt>Contribution margin</dt>
          <dd>
            {value.contribution_margin_percent === null
              ? "N/A"
              : `${value.contribution_margin_percent}%`}
          </dd>
        </div>
      </dl>
      <p className="small muted">
        Submitted revenue: {php(value.revenue.submitted_total)} · Submitted
        direct cost: {php(value.direct_cost.submitted_total)} · Unreviewed
        inputs: {value.unreviewed_count}
      </p>
      <p className="small muted">
        Maintenance is excluded. Cash advances fund expenses and are not added
        to direct cost.
      </p>
      {[
        ["Revenue breakdown", value.revenue.breakdown],
        ["Direct cost breakdown", value.direct_cost.breakdown],
      ].map(([title, items]) => (
        <div key={String(title)}>
          <h3>{String(title)}</h3>
          {(items as Breakdown[]).length ? (
            <dl className="master-fields">
              {(items as Breakdown[]).map((row) => (
                <div key={row.category}>
                  <dt>{human(row.category)}</dt>
                  <dd>
                    {php(row.reviewed_total)}{" "}
                    <small>
                      reviewed · {php(row.submitted_total)} submitted
                    </small>
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="muted">No non-voided records.</p>
          )}
        </div>
      ))}
    </>
  );
}

type LegacyQueueItem = {
  id: string; trip_number: string; completed_at: string; company_name: string;
  unreviewed_expenses: number; financials?: Financial;
};
export function LegacyReviewQueue({ identity }: { identity: Identity }) {
  const [items, setItems] = useState<LegacyQueueItem[]>(), [error, setError] = useState("");
  useEffect(() => { request<{ items: LegacyQueueItem[] }>("/financial-review/legacy")
    .then((r) => setItems(r.items)).catch((e) => setError(e.message)); }, []);
  if (!can(identity, "financial_review.read")) {
    return <ErrorState message="Financial review access is not available for this role." />;
  }
  return <div className="page-stack">
    <PageHeader title="Financial review required" description="Completed trips with legacy financial records that still need owner review." />
    {error && <ErrorState message={error} />}
    {!items && !error ? <LoadingState /> : items?.length === 0 ? <EmptyState title="No legacy financial blockers" description="Completed trips are clear of unreviewed legacy expenses." /> :
      items?.map((row) => <Card key={row.id} title={`${row.trip_number} · ${row.company_name}`}>
        <p>{dateLabel(row.completed_at)} · <strong>{row.unreviewed_expenses}</strong> expense record{row.unreviewed_expenses === 1 ? "" : "s"} need review.</p>
        {row.financials && <p className="small muted">Contribution {php(row.financials.contribution_amount)} · {human(row.financials.status)}</p>}
        <Link className="button secondary" href={`/trips/${row.id}`}>Review trip</Link>
      </Card>)}
  </div>;
}

export function FinancialPanel({
  trip,
  identity,
  revision,
}: {
  trip: Pick<TripRecord, "id" | "version" | "current_status">;
  identity: Identity;
  revision: number;
}) {
  const [financial, setFinancial] = useState<Financial>(),
    [items, setItems] = useState<Revenue[]>(),
    [total, setTotal] = useState(0),
    [offset, setOffset] = useState(0),
    [refresh, setRefresh] = useState(0);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [selected, setSelected] = useState<Revenue>(),
    [mode, setMode] = useState(""),
    [reverse, setReverse] = useState<History>();
  const [kind, setKind] = useState("BASE_TRIP_CHARGE"),
    [amount, setAmount] = useState(""),
    [description, setDescription] = useState(""),
    [reference, setReference] = useState(""),
    [reason, setReason] = useState(""),
    [correction, setCorrection] = useState("AMOUNT_CORRECTION"),
    [confirmed, setConfirmed] = useState(false);
  const command = useRef<{ body: string; key: string } | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([
      request<Financial>(`/trips/${trip.id}/financials`),
      request<{ items: Revenue[]; total: number }>(
        `/trips/${trip.id}/revenue?offset=${offset}`,
      ),
    ])
      .then(([f, r]) => {
        if (live) {
          setFinancial(f);
          setItems(r.items);
          setTotal(r.total);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [trip.id, trip.version, revision, refresh, offset]);
  function begin(next: string, row?: Revenue, event?: History) {
    setMode(next);
    setSelected(row);
    setReverse(event);
    setKind("BASE_TRIP_CHARGE");
    setAmount(row?.effective_amount ?? "");
    setDescription(row?.effective_description ?? "");
    setReference(row?.effective_reference_number ?? "");
    setReason("");
    setConfirmed(false);
    setCorrection("AMOUNT_CORRECTION");
    setError("");
    command.current = null;
  }
  async function send(path: string, body: object) {
    setBusy(true);
    setError("");
    try {
      const fingerprint = JSON.stringify({ path, body });
      if (command.current?.body !== fingerprint)
        command.current = { body: fingerprint, key: crypto.randomUUID() };
      const r = await fetch(`/api/v1${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": command.current.key,
        },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok)
        throw new Error(data?.error?.message ?? "Revenue could not be saved.");
      setNotice("Revenue history saved. Financial performance recalculated.");
      setMode("");
      setSelected(undefined);
      command.current = null;
      setRefresh((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save.");
    } finally {
      setBusy(false);
    }
  }
  const closed = trip.current_status === "COMPLETED",
    cancelled = trip.current_status === "CANCELLED";
  return (
    <Card title="Financial performance" className="master-card financial-panel">
      <div className="master-toolbar"><Link href="/trips/profitability">View trip contribution list</Link>{can(identity, "financial_review.read") && <Link href="/trips/financial-review">Financial review required</Link>}</div>
      {notice && (
        <p role="status" className="success-banner">
          {notice}
        </p>
      )}
      {error && (
        <>
          <ErrorState message={error} />
          <button
            className="button secondary"
            onClick={() => setRefresh((v) => v + 1)}
          >
            Retry financials
          </button>
        </>
      )}
      {!financial && !error ? (
        <LoadingState />
      ) : (
        financial && <FinancialSummary value={financial} />
      )}
      {can(identity, "cash_advance.read") &&
        can(identity, "financial_review.read") && (
          <GovernancePanel
            tripId={trip.id}
            identity={identity}
            revision={`${revision}-${refresh}`}
            onChange={() => setRefresh((v) => v + 1)}
          />
        )}
      <h3>Revenue history</h3>
      {!items && !error ? (
        <LoadingState />
      ) : items?.length === 0 ? (
        <p>No revenue recorded yet.</p>
      ) : (
        items?.map((row) => (
          <div className="master-card" key={row.id}>
            <strong>
              {human(row.revenue_type)} · {php(row.effective_amount)}
            </strong>
            <p className="small">
              Original: {php(row.amount)} ·{" "}
              {row.administratively_voided
                ? "Administratively voided"
                : human(row.status)}{" "}
              · {dateLabel(row.created_at)}
            </p>
            <button
              className="button secondary"
              onClick={async () => {
                try {
                  setSelected(
                    await request<Revenue>(`/trip-revenue/${row.id}`),
                  );
                  setMode("");
                } catch (e) {
                  setError(
                    e instanceof Error ? e.message : "Unable to load revenue.",
                  );
                }
              }}
            >
              View revenue history
            </button>
            {!cancelled &&
              row.status !== "VOIDED" &&
              !row.administratively_voided && (
                <>
                  {row.status === "SUBMITTED" &&
                    can(identity, "trip_revenue.review") && (
                      <button
                        className="button secondary"
                        disabled={busy}
                        onClick={() =>
                          send(`/trip-revenue/${row.id}/review`, {
                            expected_sequence: row.sequence,
                          })
                        }
                      >
                        Review revenue
                      </button>
                    )}
                  {can(identity, "closed_trip_adjustments.create") && (
                    <button
                      className="button secondary"
                      onClick={() => begin("correct", row)}
                    >
                      Adjust revenue
                    </button>
                  )}
                  {!closed && can(identity, "trip_revenue.void") && (
                    <button
                      className="button secondary"
                      onClick={() => begin("void", row)}
                    >
                      Void revenue
                    </button>
                  )}
                </>
              )}
          </div>
        ))
      )}
      <div className="master-toolbar">
        <button
          className="button secondary"
          disabled={offset === 0}
          onClick={() => setOffset((v) => Math.max(0, v - 20))}
        >
          Previous revenue
        </button>
        <span>{total} revenue records</span>
        <button
          className="button secondary"
          disabled={offset + 20 >= total}
          onClick={() => setOffset((v) => v + 20)}
        >
          More revenue
        </button>
      </div>
      {selected && !mode && (
        <section>
          <h3>Original submission and correction history</h3>
          <p>
            Original {php(selected.amount)} · Current effective{" "}
            {php(selected.effective_amount)} · Actor {selected.created_by}
          </p>
          <p>
            {selected.effective_description} ·{" "}
            {selected.effective_reference_number}
          </p>
          {selected.reviewed_at && (
            <p>Reviewed {dateLabel(selected.reviewed_at)}</p>
          )}
          {selected.history?.map((event) => (
            <div key={event.id}>
              <p>
                {event.adjustment_status} · {human(event.field_name)}:{" "}
                {adjustmentValue(event.old_value, event.field_name)} →{" "}
                {adjustmentValue(event.new_value, event.field_name)}
              </p>
              <p>
                {event.reason} · {dateLabel(event.created_at)} ·{" "}
                {event.created_by}
              </p>
              {event.adjustment_status === "APPLIED" &&
                can(identity, "closed_trip_adjustments.reverse") && (
                  <button
                    className="button secondary"
                    onClick={() => begin("reverse", selected, event)}
                  >
                    Reverse revenue adjustment
                  </button>
                )}
            </div>
          ))}
        </section>
      )}
      {!cancelled && !mode && can(identity, "trip_revenue.create") && (
        <button className="button primary" onClick={() => begin("add")}>
          Add revenue
        </button>
      )}
      {mode && (
        <form
          className="master-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (mode === "add") {
              if (!validDecimal(amount, 2, "10000000")) {
                setError(
                  "Enter a positive PHP amount with at most two decimal places.",
                );
                return;
              }
              if (kind === "OTHER" && description.trim().length < 3) {
                setError("Other requires an explanation.");
                return;
              }
              void send(`/trips/${trip.id}/revenue`, {
                revenue_type: kind,
                amount,
                description: description || null,
                reference_number: reference || null,
              });
              return;
            }
            if (!selected || !confirmed || !validReason(reason)) {
              setError(
                "Confirm the permanent entry and provide at least 10 non-whitespace reason characters.",
              );
              return;
            }
            if (mode === "reverse") {
              void send(`/adjustments/${reverse!.id}/reverse`, {
                expected_sequence: selected.sequence,
                reason,
              });
              return;
            }
            if (mode === "void") {
              void send(`/trip-revenue/${selected.id}/void`, {
                expected_sequence: selected.sequence,
                reason,
              });
              return;
            }
            if (
              correction === "AMOUNT_CORRECTION" &&
              !validDecimal(amount, 2, "10000000")
            ) {
              setError("Enter a valid positive corrected amount.");
              return;
            }
            void send(`/trip-revenue/${selected.id}/correct`, {
              target_id: selected.id,
              expected_sequence: selected.sequence,
              reason,
              adjustment_type: correction,
              new_value:
                correction === "VOID_ADJUSTMENT"
                  ? null
                  : correction === "AMOUNT_CORRECTION"
                    ? amount
                    : correction === "DESCRIPTION_CORRECTION"
                      ? description || null
                      : reference || null,
            });
          }}
        >
          <h3>
            {mode === "add"
              ? "Add revenue"
              : mode === "correct"
                ? "Adjust revenue"
                : mode === "reverse"
                  ? "Reverse revenue adjustment"
                  : "Void revenue"}
          </h3>
          {mode === "add" && (
            <label>
              Revenue type
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {kinds.map((k) => (
                  <option key={k} value={k}>
                    {human(k)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {mode === "correct" && (
            <label>
              Revenue correction type
              <select
                value={correction}
                onChange={(e) => setCorrection(e.target.value)}
              >
                {[
                  "AMOUNT_CORRECTION",
                  "REFERENCE_CORRECTION",
                  "DESCRIPTION_CORRECTION",
                  "VOID_ADJUSTMENT",
                ].map((k) => (
                  <option key={k} value={k}>
                    {human(k)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {(mode === "add" ||
            (mode === "correct" && correction === "AMOUNT_CORRECTION")) && (
            <label>
              Revenue amount (PHP)
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                inputMode="decimal"
                required
              />
            </label>
          )}
          {(mode === "add" ||
            (mode === "correct" && correction === "REFERENCE_CORRECTION")) && (
            <label>
              Revenue reference
              <input
                maxLength={120}
                value={reference}
                onChange={(e) => setReference(e.target.value)}
              />
            </label>
          )}
          {(mode === "add" ||
            (mode === "correct" &&
              correction === "DESCRIPTION_CORRECTION")) && (
            <label>
              Revenue description
              <textarea
                maxLength={2000}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
          )}
          {mode !== "add" && (
            <>
              <label>
                Revenue correction reason
                <textarea
                  maxLength={2000}
                  required
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                  required
                />
                {mode === "void"
                  ? "The original revenue will remain in history. This void is permanent."
                  : "This will not overwrite the original record. A permanent adjustment entry will be created."}
              </label>
            </>
          )}
          <button className="button primary" disabled={busy}>
            {busy
              ? "Saving…"
              : mode === "add"
                ? "Save revenue"
                : "Confirm revenue change"}
          </button>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => setMode("")}
          >
            Cancel revenue form
          </button>
        </form>
      )}
    </Card>
  );
}

type ListRow = Financial & {
  trip_number: string;
  customer_name: string;
  current_status: string;
};
type Choice = {
  id: string;
  company_name?: string;
  unit_number?: string;
  first_name?: string;
  last_name?: string;
};
export function ProfitabilityList({ identity }: { identity: Identity }) {
  const [filters, setFilters] = useState<Record<string, string>>({}),
    [offset, setOffset] = useState(0),
    [result, setResult] = useState<{ items: ListRow[]; total: number }>(),
    [error, setError] = useState(""),
    [refresh, setRefresh] = useState(0),
    [choices, setChoices] = useState<Record<string, Choice[]>>({});
  const query = new URLSearchParams({
    ...filters,
    limit: "20",
    offset: String(offset),
  }).toString();
  useEffect(() => {
    let live = true;
    request<{ items: ListRow[]; total: number }>(
      `/profitability/trips?${query}`,
    )
      .then((p) => {
        if (live) {
          setResult(p);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [query, refresh]);
  useEffect(() => {
    let live = true;
    for (const domain of ["customers", "vehicles", "drivers"] as const) {
      if (can(identity, `${domain}.read`))
        void request<{ items: Choice[] }>(`/${domain}?limit=100`)
          .then((p) => {
            if (live) setChoices((old) => ({ ...old, [domain]: p.items }));
          })
          .catch(() => {});
    }
    return () => {
      live = false;
    };
  }, [identity]);
  function filter(key: string, value: string) {
    setOffset(0);
    setFilters((old) => {
      const next = { ...old };
      if (value) next[key] = value;
      else delete next[key];
      return next;
    });
  }
  return (
    <div className="master-page">
      <PageHeader
        title="Trip contribution"
        description="Reviewed operational revenue and direct costs. Maintenance and cash advances are excluded."
      />
      <Link href="/dispatch">Back to dispatch</Link>
      <Card className="master-card">
        <div className="master-toolbar">
          <label>
            Search financial trips
            <input
              value={filters.search ?? ""}
              onChange={(e) => filter("search", e.target.value)}
              maxLength={160}
            />
          </label>
          {(
            [
              ["customers", "customer_id", "Customer"],
              ["vehicles", "vehicle_id", "Vehicle"],
              ["drivers", "driver_id", "Driver"],
            ] as const
          ).map(([domain, key, label]) => (
            <label key={key}>
              {label}
              <select
                value={filters[key] ?? ""}
                onChange={(e) => filter(key, e.target.value)}
              >
                <option value="">All</option>
                {choices[domain]?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.company_name ??
                      c.unit_number ??
                      `${c.first_name} ${c.last_name}`}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <label>
            Trip status
            <select
              value={filters.status ?? ""}
              onChange={(e) => filter("status", e.target.value)}
            >
              <option value="">All</option>
              {tripStatuses.map((s) => (
                <option key={s} value={s}>
                  {human(s)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Pickup from
            <input
              type="date"
              onChange={(e) =>
                filter(
                  "date_from",
                  e.target.value ? `${e.target.value}T00:00:00+08:00` : "",
                )
              }
            />
          </label>
          <label>
            Pickup through
            <input
              type="date"
              onChange={(e) =>
                filter(
                  "date_to",
                  e.target.value
                    ? `${e.target.value}T23:59:59.999999+08:00`
                    : "",
                )
              }
            />
          </label>
          <label>
            Order
            <select
              value={filters.direction ?? "desc"}
              onChange={(e) => filter("direction", e.target.value)}
            >
              <option value="desc">Newest pickup</option>
              <option value="asc">Oldest pickup</option>
            </select>
          </label>
        </div>
        {error && (
          <>
            <ErrorState message={error} />
            <button
              className="button secondary"
              onClick={() => setRefresh((v) => v + 1)}
            >
              Retry contribution list
            </button>
          </>
        )}
        {!result && !error ? (
          <LoadingState />
        ) : result?.items.length === 0 ? (
          <EmptyState
            title="No matching trips"
            description="Choose another filter or create a trip in Dispatch."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {[
                    "Trip",
                    "Customer",
                    "Revenue",
                    "Direct cost",
                    "Contribution",
                    "Margin",
                    "Status",
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result?.items.map((r) => (
                  <tr key={r.trip_id}>
                    <td>
                      <Link href={`/trips/${r.trip_id}`}>{r.trip_number}</Link>
                    </td>
                    <td>{r.customer_name}</td>
                    <td>{php(r.revenue.effective_total)}</td>
                    <td>{php(r.direct_cost.effective_total)}</td>
                    <td>{php(r.contribution_amount)}</td>
                    <td>
                      {r.contribution_margin_percent === null
                        ? "N/A"
                        : `${r.contribution_margin_percent}%`}
                    </td>
                    <td>{r.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="master-toolbar">
          <button
            className="button secondary"
            disabled={!offset}
            onClick={() => setOffset((v) => Math.max(0, v - 20))}
          >
            Previous financial trips
          </button>
          <span>{result?.total ?? 0} trips</span>
          <button
            className="button secondary"
            disabled={!result || offset + 20 >= result.total}
            onClick={() => setOffset((v) => v + 20)}
          >
            More financial trips
          </button>
        </div>
      </Card>
    </div>
  );
}
