"use client";
import { useEffect, useRef, useState } from "react";
import { ErrorState, LoadingState } from "@fleetpilot/ui";
import { can } from "@fleetpilot/auth";
import type { Identity } from "@fleetpilot/types";
import { request } from "@/lib/client";
import { php, validDecimal } from "@/lib/money";
import { dateLabel, human } from "@/lib/trips";
import { validReason } from "./adjustments";

type Entry = {
  id: string;
  entry_type: string;
  amount: string;
  reason: string;
  created_by: string;
  created_at: string;
  reversed: boolean;
};
export type Advance = {
  id: string;
  amount_issued: string;
  applied: string;
  returned: string;
  outstanding: string;
  status: string;
  issued_at: string;
  history: Entry[];
};
export type ReviewState = {
  financials?: {
    revenue: { effective_total: string };
    direct_cost: { effective_total: string };
    contribution_amount: string;
    contribution_margin_percent: string | null;
  };
  status: string;
  blockers: string[];
  latest_event_id: string | null;
  legacy_expenses?: {
    id: string; category: string; amount: string; original_amount: string;
    occurred_at: string; description: string | null; first_name: string; last_name: string;
  }[];
  history: {
    id: string;
    status: string;
    reason: string;
    created_by: string;
    created_at: string;
  }[];
};
type Expense = {
  id: string;
  category: string;
  amount: string;
  status: string;
  administratively_voided: boolean;
};
export function AdvanceSummary({ value }: { value: Advance }) {
  return (
    <>
      <p>
        <strong>{human(value.status)}</strong> · {dateLabel(value.issued_at)}
      </p>
      <dl className="master-fields">
        {[
          ["Advance issued", value.amount_issued],
          ["Expenses applied", value.applied],
          ["Cash returned", value.returned],
          ["Outstanding", value.outstanding],
        ].map(([label, amount]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{php(amount)}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}
export function ReviewChecklist({ value }: { value: ReviewState }) {
  return (
    <>
      <p>
        Financial review: <strong>{human(value.status)}</strong>
      </p>
      {value.blockers.length > 0 ? (
        <ul>
          {value.blockers.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : (
        <p className="small muted">
          Revenue and direct expenses reviewed. Cash advances reconciled. No
          recorded settlement conflicts.
        </p>
      )}
    </>
  );
}
export function GovernancePanel({
  tripId,
  identity,
  revision,
  onChange,
}: {
  tripId: string;
  identity: Identity;
  revision: string;
  onChange: () => void;
}) {
  const [advances, setAdvances] = useState<Advance[]>(),
    [review, setReview] = useState<ReviewState>(),
    [expenses, setExpenses] = useState<Expense[]>([]),
    [offset, setOffset] = useState(0),
    [total, setTotal] = useState(0),
    [expenseOffset, setExpenseOffset] = useState(0),
    [expenseTotal, setExpenseTotal] = useState(0),
    [historyOffset, setHistoryOffset] = useState(0);
  const [mode, setMode] = useState(""),
    [selected, setSelected] = useState<Advance>(),
    [entry, setEntry] = useState<Entry>(),
    [amount, setAmount] = useState(""),
    [expense, setExpense] = useState(""),
    [reason, setReason] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [reviewConfirmed, setReviewConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [refresh, setRefresh] = useState(0);
  const command = useRef<{ document: string; key: string } | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([
      request<{ items: Advance[]; total: number }>(
        `/trips/${tripId}/cash-advances?offset=${offset}`,
      ),
      request<ReviewState>(
        `/trips/${tripId}/financial-review?offset=${historyOffset}`,
      ),
      request<{ items: Expense[]; total: number }>(
        `/trips/${tripId}/expenses?limit=100&offset=${expenseOffset}`,
      ),
    ])
      .then(([a, r, e]) => {
        if (live) {
          setAdvances(a.items);
          setTotal(a.total);
          setReview(r);
          setExpenses(e.items);
          setExpenseTotal(e.total);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [tripId, revision, refresh, offset, expenseOffset, historyOffset]);
  function begin(next: string, a?: Advance, e?: Entry) {
    setMode(next);
    setSelected(a);
    setEntry(e);
    setAmount("");
    setExpense("");
    setReason("");
    setConfirmed(false);
    setError("");
    command.current = null;
  }
  async function send(path: string, body: object) {
    const document = JSON.stringify({ path, body });
    if (command.current?.document !== document)
      command.current = { document, key: crypto.randomUUID() };
    setBusy(true);
    setError("");
    try {
      const r = await fetch(`/api/v1${path}`, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": command.current.key,
        },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok)
        throw new Error(
          data?.error?.message ??
            "Unable to save. Reload and check the current state.",
        );
      setReviewConfirmed(false);
      setNotice("Financial history saved.");
      setMode("");
      command.current = null;
      setRefresh((v) => v + 1);
      onChange();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Unable to save. Retry the same command.",
      );
    } finally {
      setBusy(false);
    }
  }
  if (
    !can(identity, "cash_advance.read") ||
    !can(identity, "financial_review.read")
  )
    return null;
  return (
    <section className="governance-panel">
      <h3>Cash advance &amp; settlement</h3>
      <p className="small muted">
        Advances fund expenses; they do not add another trip cost. Settlement is
        online and performed by an authorized operator.
      </p>
      {error && (
        <>
          <ErrorState message={error} />
          <button
            className="button secondary"
            onClick={() => setRefresh((v) => v + 1)}
          >
            Reload settlement
          </button>
        </>
      )}
      {notice && (
        <p role="status" className="success-banner">
          {notice}
        </p>
      )}
      {!advances && !error ? (
        <LoadingState />
      ) : advances?.length === 0 ? (
        <p>No cash advances recorded.</p>
      ) : (
        advances?.map((a) => (
          <div className="master-card" key={a.id}>
            <AdvanceSummary value={a} />
            {a.status !== "VOIDED" && can(identity, "cash_advance.settle") && (
              <>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => begin("apply", a)}
                >
                  Apply expense
                </button>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => begin("return", a)}
                >
                  Record cash return
                </button>
              </>
            )}
            {a.history.length === 0 &&
              a.status !== "VOIDED" &&
              can(identity, "cash_advance.void") && (
                <button
                  className="button secondary"
                  onClick={() => begin("void", a)}
                >
                  Void advance
                </button>
              )}
            <h4>Settlement history</h4>
            {a.history.length === 0 ? (
              <p className="small muted">No settlement entries.</p>
            ) : (
              a.history.map((e) => (
                <div key={e.id}>
                  <p>
                    {human(e.entry_type)} · {php(e.amount)}{" "}
                    {e.reversed ? "· Reversed" : ""}
                  </p>
                  <p className="small muted">
                    {e.reason} · {dateLabel(e.created_at)} · Actor{" "}
                    {e.created_by}
                  </p>
                  {!e.reversed &&
                    ["EXPENSE_APPLIED", "CASH_RETURNED"].includes(
                      e.entry_type,
                    ) &&
                    can(identity, "cash_advance.settle") && (
                      <button
                        className="button secondary"
                        onClick={() => begin("reverse", a, e)}
                      >
                        Reverse settlement entry
                      </button>
                    )}
                </div>
              ))
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
          Previous advances
        </button>
        <span>{total} advances</span>
        <button
          className="button secondary"
          disabled={offset + 20 >= total}
          onClick={() => setOffset((v) => v + 20)}
        >
          More advances
        </button>
      </div>
      {can(identity, "cash_advance.create") && (
        <>
          <button className="button primary" onClick={() => begin("issue")}>
            Issue cash advance
          </button>
          <button
            className="button secondary"
            onClick={() => begin("reconcile")}
          >
            Reconcile recorded advance
          </button>
        </>
      )}
      {mode && (
        <form
          className="master-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!confirmed) {
              setError("Confirm the permanent financial entry.");
              return;
            }
            if (
              ["issue", "return"].includes(mode) &&
              !validDecimal(amount, 2, "10000000")
            ) {
              setError(
                "Enter a positive PHP amount with at most two decimal places.",
              );
              return;
            }
            if (
              !["issue", "reconcile"].includes(mode) &&
              !validReason(reason)
            ) {
              setError("Provide at least 10 non-whitespace reason characters.");
              return;
            }
            if (["apply", "reconcile"].includes(mode) && !expense) {
              setError("Select an expense record.");
              return;
            }
            if (mode === "issue")
              void send(`/trips/${tripId}/cash-advances`, {
                amount,
                currency: "PHP",
                purpose: reason || null,
              });
            else if (mode === "reconcile")
              void send(`/trips/${tripId}/cash-advances`, {
                source_expense_id: expense,
                purpose: reason || null,
              });
            else if (selected) {
              const suffix =
                mode === "apply"
                  ? "apply-expense"
                  : mode === "return"
                    ? "cash-return"
                    : mode === "reverse"
                      ? `entries/${entry?.id}/reverse`
                      : "void";
              void send(`/cash-advances/${selected.id}/${suffix}`, {
                reason,
                ...(mode === "apply"
                  ? { expense_id: expense }
                  : mode === "return"
                    ? { amount, currency: "PHP" }
                    : {}),
              });
            }
          }}
        >
          <h4>{human(mode)} cash advance</h4>
          {["issue", "return"].includes(mode) && (
            <label>
              Cash amount (PHP)
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                inputMode="decimal"
                required
                maxLength={14}
              />
            </label>
          )}
          {["apply", "reconcile"].includes(mode) && (
            <>
              <label>
                Expense record
                <select
                  value={expense}
                  required
                  onChange={(e) => setExpense(e.target.value)}
                >
                  <option value="">Select record</option>
                  {expenses
                    .filter((e) =>
                      mode === "reconcile"
                        ? e.category === "DRIVER_CASH_ADVANCE" &&
                          e.status !== "VOIDED" &&
                          !e.administratively_voided
                        : e.category !== "DRIVER_CASH_ADVANCE" &&
                          e.status === "REVIEWED" &&
                          !e.administratively_voided,
                    )
                    .map((e) => (
                      <option key={e.id} value={e.id}>
                        {human(e.category)} · {php(e.amount)} · {e.id}
                      </option>
                    ))}
                </select>
              </label>
              <div className="master-toolbar">
                <button
                  type="button"
                  className="button secondary"
                  disabled={expenseOffset === 0}
                  onClick={() => setExpenseOffset((v) => Math.max(0, v - 100))}
                >
                  Previous expense records
                </button>
                <button
                  type="button"
                  className="button secondary"
                  disabled={expenseOffset + 100 >= expenseTotal}
                  onClick={() => setExpenseOffset((v) => v + 100)}
                >
                  More expense records
                </button>
              </div>
            </>
          )}
          <label>
            {["issue", "reconcile"].includes(mode)
              ? "Advance purpose (optional)"
              : "Settlement reason"}
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={2000}
              required={!["issue", "reconcile"].includes(mode)}
            />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I confirm this permanent financial entry. Original records remain in
            history.
          </label>
          <button className="button primary" disabled={busy}>
            {busy ? "Saving…" : "Save settlement entry"}
          </button>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => setMode("")}
          >
            Cancel settlement
          </button>
        </form>
      )}
      <h3>Trip financial review</h3>
      {review && (
        <>
          <ReviewChecklist value={review} />
          {(review.legacy_expenses?.length ?? 0) > 0 && (
            <div className="master-card">
              <h4>Financial review blockers</h4>
              <p className="small muted">
                Legacy completed-trip expenses remain immutable. Accept valid records here; use Administrative adjustments to correct or void a record before accepting it.
              </p>
              {review.legacy_expenses?.map((row) => (
                <div className="master-row" key={row.id}>
                  <strong>{human(row.category)} · {php(row.amount)}</strong>
                  <p className="small">{dateLabel(row.occurred_at)} · {row.first_name} {row.last_name}</p>
                  {row.description && <p className="small muted">{row.description}</p>}
                  {can(identity, "financial_review.approve") && (
                    <button className="button secondary" disabled={busy} onClick={() => void send(`/expenses/${row.id}/legacy-review`, { confirmed: true })}>
                      Accept legacy expense
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          {review.financials && (
            <p className="small muted">
              Review snapshot · Revenue{" "}
              {php(review.financials.revenue.effective_total)} · Direct cost{" "}
              {php(review.financials.direct_cost.effective_total)} ·
              Contribution {php(review.financials.contribution_amount)} · Margin{" "}
              {review.financials.contribution_margin_percent === null
                ? "N/A"
                : `${review.financials.contribution_margin_percent}%`}
            </p>
          )}
          {can(identity, "financial_review.approve") &&
            review.status !== "APPROVED" && (
              <>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={reviewConfirmed}
                    onChange={(e) => setReviewConfirmed(e.target.checked)}
                  />
                  I have checked revenue, costs, adjustments and advances, and
                  all known financial records have synchronized.
                </label>
                <button
                  className="button secondary"
                  disabled={busy || !reviewConfirmed}
                  onClick={() =>
                    void send(`/trips/${tripId}/financial-review/start`, {
                      expected_event_id: review.latest_event_id,
                      records_confirmed: true,
                    })
                  }
                >
                  Review financials
                </button>
                <button
                  className="button primary"
                  disabled={
                    busy || !reviewConfirmed || review.blockers.length > 0
                  }
                  onClick={() =>
                    void send(`/trips/${tripId}/financial-review/approve`, {
                      expected_event_id: review.latest_event_id,
                      records_confirmed: true,
                    })
                  }
                >
                  Approve financial review
                </button>
              </>
            )}
          <h4>Financial review history</h4>
          {review.history.length === 0 ? (
            <p className="small muted">No financial review events.</p>
          ) : (
            review.history.map((e) => (
              <div key={e.id}>
                <p>
                  {human(e.status)} · {dateLabel(e.created_at)}
                </p>
                <p className="small muted">
                  {e.reason.replaceAll("_", " ")} · Actor {e.created_by}
                </p>
              </div>
            ))
          )}
          <div className="master-toolbar">
            <button
              className="button secondary"
              disabled={historyOffset === 0}
              onClick={() => setHistoryOffset((v) => Math.max(0, v - 20))}
            >
              Previous reviews
            </button>
            <button
              className="button secondary"
              disabled={review.history.length < 20}
              onClick={() => setHistoryOffset((v) => v + 20)}
            >
              More reviews
            </button>
          </div>
        </>
      )}
    </section>
  );
}
