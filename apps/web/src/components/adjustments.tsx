"use client";
import { useEffect, useRef, useState } from "react";
import { ErrorState, LoadingState } from "@fleetpilot/ui";
import { can } from "@fleetpilot/auth";
import type { Identity } from "@fleetpilot/types";
import { request } from "@/lib/client";
import { dateLabel, human } from "@/lib/trips";
import { php, validDecimal } from "@/lib/money";

type Adjustment = {
  id: string;
  expense_id: string;
  sequence: number;
  adjustment_type: string;
  field_name: string;
  old_value: string | boolean | null;
  new_value: string | boolean | null;
  amount_delta: string | null;
  reason: string;
  created_at: string;
  created_by: string;
  status: string;
  reverses_id: string | null;
};
type Effective = { amount: string; sequence: number; voided: boolean };
const kinds = [
  "AMOUNT_CORRECTION",
  "REFERENCE_CORRECTION",
  "DESCRIPTION_CORRECTION",
  "ODOMETER_CORRECTION",
  "VOID_ADJUSTMENT",
];
export const validReason = (value: string) =>
  value.replace(/\s/g, "").length >= 10;
export const adjustmentValue = (
  value: string | boolean | null,
  field: string,
) =>
  value === null
    ? "Not recorded"
    : field === "amount"
      ? php(String(value))
      : String(value);

export function Adjustments({
  tripId,
  identity,
  expenses,
  onChanged,
}: {
  tripId: string;
  identity: Identity;
  expenses: { id: string; category: string; amount: string }[];
  onChanged: () => void;
}) {
  const [items, setItems] = useState<Adjustment[]>(),
    [total, setTotal] = useState(0),
    [offset, setOffset] = useState(0),
    [refresh, setRefresh] = useState(0);
  const [form, setForm] = useState(false),
    [target, setTarget] = useState(""),
    [kind, setKind] = useState("AMOUNT_CORRECTION"),
    [value, setValue] = useState(""),
    [reason, setReason] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const [reversal, setReversal] = useState<Adjustment>(),
    [effective, setEffective] = useState<Effective>(),
    [original, setOriginal] = useState<string>(),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const command = useRef<{ body: string; key: string } | undefined>(undefined);
  useEffect(() => {
    let live = true;
    request<{ items: Adjustment[]; total: number }>(
      `/trips/${tripId}/adjustments?offset=${offset}`,
    )
      .then((p) => {
        if (live) {
          setItems(p.items);
          setTotal(p.total);
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [tripId, offset, refresh]);
  useEffect(() => {
    if (!target) return;
    let live = true;
    request<{ effective: Effective; current: { amount: string } }>(
      `/expenses/${target}`,
    )
      .then((p) => {
        if (live) {
          setEffective(p.effective);
          setOriginal(p.current.amount);
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [target, refresh]);
  function begin(row?: Adjustment) {
    setReversal(row);
    setTarget(row?.expense_id ?? "");
    setEffective(undefined);
    setOriginal(undefined);
    setReason("");
    setValue("");
    setConfirmed(false);
    setError("");
    setForm(true);
  }
  return (
    <section className="audit-history" aria-label="Administrative adjustments">
      <h3>Administrative adjustments</h3>
      <p className="small muted">
        Completed trips remain closed. Original financial records are preserved.
      </p>
      {error && (
        <>
          <ErrorState message={error} />
          <button
            className="button secondary"
            onClick={() => {
              setError("");
              setRefresh((n) => n + 1);
            }}
          >
            Reload adjustments
          </button>
        </>
      )}
      {notice && (
        <p role="status" className="success-banner">
          {notice}
        </p>
      )}
      {!items ? (
        <LoadingState />
      ) : items.length === 0 ? (
        <p>No administrative adjustments.</p>
      ) : (
        items.map((row) => (
          <div key={row.id} className="master-row">
            <strong>
              {human(row.adjustment_type)} · {human(row.status)}
            </strong>
            <p>
              {dateLabel(row.created_at)} · Record {row.expense_id} · Actor{" "}
              {row.created_by}
            </p>
            <p>
              {human(row.field_name)}:{" "}
              {adjustmentValue(row.old_value, row.field_name)} →{" "}
              {adjustmentValue(row.new_value, row.field_name)}
              {row.amount_delta !== null &&
                ` · Adjustment ${row.amount_delta} PHP`}
            </p>
            <p>{row.reason}</p>
            {row.status === "APPLIED" &&
              can(identity, "closed_trip_adjustments.reverse") && (
                <button className="button secondary" onClick={() => begin(row)}>
                  Reverse adjustment
                </button>
              )}
          </div>
        ))
      )}
      {total > 50 && (
        <div className="master-actions">
          <button
            className="button secondary"
            disabled={!offset}
            onClick={() => setOffset((n) => n - 50)}
          >
            Previous adjustments
          </button>
          <button
            className="button secondary"
            disabled={offset + 50 >= total}
            onClick={() => setOffset((n) => n + 50)}
          >
            More adjustments
          </button>
        </div>
      )}
      {!form && can(identity, "closed_trip_adjustments.create") && (
        <button className="button secondary" onClick={() => begin()}>
          Create adjustment
        </button>
      )}
      {form && (
        <form
          className="master-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            if (!validReason(reason)) {
              setError(
                "Provide at least 10 non-whitespace characters for the reason.",
              );
              return;
            }
            if (!effective || !confirmed) return;
            if (
              !reversal &&
              (kind === "AMOUNT_CORRECTION" ||
                kind === "ODOMETER_CORRECTION") &&
              !validDecimal(
                value,
                kind === "AMOUNT_CORRECTION" ? 2 : 1,
                "10000000",
                kind === "ODOMETER_CORRECTION",
              )
            ) {
              setError(
                "Enter a valid decimal value within the permitted range.",
              );
              return;
            }
            setBusy(true);
            try {
              const body = {
                expected_sequence: effective.sequence,
                reason,
                ...(!reversal
                  ? {
                      target_id: target,
                      adjustment_type: kind,
                      new_value:
                        kind === "VOID_ADJUSTMENT" ? null : value || null,
                    }
                  : {}),
              };
              const path = reversal
                ? `/adjustments/${reversal.id}/reverse`
                : `/trips/${tripId}/adjustments`;
              const serialized = JSON.stringify({ path, body });
              if (command.current?.body !== serialized)
                command.current = {
                  body: serialized,
                  key: crypto.randomUUID(),
                };
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
                throw new Error(data?.error?.message ?? "Adjustment failed.");
              setForm(false);
              setNotice(
                reversal
                  ? "Adjustment reversed. History is preserved."
                  : "Adjustment applied. Original record is unchanged.",
              );
              setRefresh((n) => n + 1);
              onChanged();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Adjustment failed.");
            } finally {
              setBusy(false);
            }
          }}
        >
          <h4>{reversal ? "Reverse adjustment" : "Create adjustment"}</h4>
          {!reversal && (
            <>
              <label>
                Expense record
                <select
                  required
                  value={target}
                  onChange={(e) => {
                    setEffective(undefined);
                    setTarget(e.target.value);
                  }}
                >
                  <option value="">Select an expense</option>
                  {expenses.map((x) => (
                    <option key={x.id} value={x.id}>
                      {human(x.category)} · {php(x.amount)} ·{" "}
                      {x.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Correction type
                <select value={kind} onChange={(e) => setKind(e.target.value)}>
                  {kinds.map((x) => (
                    <option key={x} value={x}>
                      {human(x)}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          {effective && (
            <p>
              Original at closeout: {php(original ?? "0")} · Current effective
              value: {effective.voided ? "Voided" : php(effective.amount)}
            </p>
          )}
          {!reversal && kind !== "VOID_ADJUSTMENT" && (
            <label>
              Corrected value
              <input
                required={
                  kind === "AMOUNT_CORRECTION" || kind === "ODOMETER_CORRECTION"
                }
                value={value}
                onChange={(e) => setValue(e.target.value)}
                maxLength={kind === "REFERENCE_CORRECTION" ? 120 : 2000}
              />
            </label>
          )}
          {kind === "ODOMETER_CORRECTION" && !reversal && (
            <p className="small muted">
              Historical fuel reading only. Vehicle current and trusted readings
              will not change.
            </p>
          )}
          <label>
            Adjustment reason
            <textarea
              required
              minLength={10}
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              required
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            This will not overwrite the original record. A permanent adjustment
            entry will be created.
          </label>
          <div className="master-actions">
            <button
              className="button primary"
              disabled={busy || !effective || !confirmed}
            >
              {busy
                ? "Saving…"
                : reversal
                  ? "Confirm reversal"
                  : "Apply adjustment"}
            </button>
            <button
              type="button"
              className="button secondary"
              disabled={busy}
              onClick={() => setForm(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
