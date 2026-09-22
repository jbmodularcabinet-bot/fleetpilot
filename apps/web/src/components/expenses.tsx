"use client";
import { useEffect, useRef, useState } from "react";
import { Card, ErrorState, LoadingState, StatusBadge } from "@fleetpilot/ui";
import { can } from "@fleetpilot/auth";
import type { Identity } from "@fleetpilot/types";
import { request } from "@/lib/client";
import { queueExpense, sync, validateFile } from "@/lib/offline";
import { fuelEstimate, php, validDecimal } from "@/lib/money";
import { dateLabel, human, localInput, type TripRecord } from "@/lib/trips";

import { Adjustments } from "./adjustments";

const categories = [
  "FUEL",
  "TOLL",
  "PARKING",
  "DRIVER_ALLOWANCE",
  "DRIVER_CASH_ADVANCE",
  "HELPER_ALLOWANCE",
  "LOADING_FEE",
  "UNLOADING_FEE",
  "SUBCONTRACTOR",
  "OTHER",
];
interface Cost {
  id: string;
  category: string;
  amount: string;
  status: string;
  administratively_voided?: boolean;
  adjustment_sequence?: number;
  occurred_at: string;
  liters: string | null;
  price_per_liter: string | null;
  odometer: string | null;
  description: string | null;
  vendor_name: string | null;
  reference_number: string | null;
  trip_number: string;
  unit_number: string;
  first_name: string;
  last_name: string;
}
interface Revision extends Cost {
  revision_number: number;
  created_at: string;
  created_by: string;
  reason: string | null;
}
interface Detail {
  effective: { amount: string; voided: boolean; sequence: number };
  id: string;
  current: Revision;
  revisions: Revision[];
  evidence: {
    id: string;
    original_filename: string;
    status: string;
    uploaded_at: string;
    uploaded_by: string;
  }[];
  submitted_at: string;
  submitted_by: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  review_notes: string | null;
  void_reason: string | null;
}
interface Page {
  items: Cost[];
  total: number;
  submitted_total: string;
  reviewed_total: string;
  summary: {
    category: string;
    submitted_total: string;
    reviewed_total: string;
  }[];
}
async function post<T>(path: string, body: unknown, key: string): Promise<T> {
  const r = await fetch(`/api/v1${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data?.error?.message ?? "Unable to save expense.");
  return data.result as T;
}
function Receipt({ id, name }: { id: string; name: string }) {
  const [failed, setFailed] = useState(false),
    [retry, setRetry] = useState(0);
  return failed ? (
    <>
      <ErrorState message="Receipt unavailable." />
      <button
        className="button secondary"
        onClick={() => {
          setFailed(false);
          setRetry(retry + 1);
        }}
      >
        Retry receipt
      </button>
    </>
  ) : (
    <a href={`/api/v1/expense-evidence/${id}`} target="_blank" rel="noreferrer">
      {/* eslint-disable-next-line @next/next/no-img-element -- authenticated private receipt */}
      <img
        key={retry}
        src={`/api/v1/expense-evidence/${id}`}
        alt={name}
        onError={() => setFailed(true)}
        style={{ maxWidth: "100%", maxHeight: 180 }}
      />
    </a>
  );
}
export function ExpenseForm({
  trip,
  own,
  initial,
  onDone,
}: {
  trip: TripRecord;
  own: boolean;
  initial?: Detail;
  onDone: () => void;
}) {
  const original = initial?.current;
  const [category, setCategory] = useState(original?.category ?? "FUEL");
  const [values, setValues] = useState<Record<string, string>>({
    amount: original?.amount ?? "",
    liters: original?.liters ?? "",
    price_per_liter: original?.price_per_liter ?? "",
    odometer: original?.odometer ?? "",
    description: original?.description ?? "",
    vendor_name: original?.vendor_name ?? "",
    reference_number: original?.reference_number ?? "",
    occurred_at: localInput(original?.occurred_at ?? new Date().toISOString()),
    reason: "",
  });
  const [files, setFiles] = useState<File[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const [accepted, setAccepted] = useState(false);
  const operation = useRef<{
    body: string;
    key: string;
    result?: { expense: Detail; trip_version: number };
    uploaded: number;
    receiptKeys: string[];
  } | null>(null);
  const estimate = fuelEstimate(values.liters, values.price_per_liter);
  return (
    <form
      className="master-form"
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");
        setMessage("");
        try {
          if (category === "FUEL") {
            if (
              !validDecimal(values.liters, 3, "10000") ||
              !validDecimal(values.price_per_liter, 4, "10000") ||
              !estimate ||
              !validDecimal(estimate, 2, "10000000")
            )
              throw new Error(
                "Enter positive liters (up to 10,000; 3 decimals) and price (up to PHP 10,000; 4 decimals). Total must be PHP 0.01–10,000,000.",
              );
            if (
              values.odometer &&
              !validDecimal(values.odometer, 1, "10000000", true)
            )
              throw new Error(
                "Odometer must be 0–10,000,000 km with at most one decimal.",
              );
          } else if (!validDecimal(values.amount, 2, "10000000")) {
            throw new Error(
              "Enter a plain positive PHP amount up to 10,000,000 with at most two decimals.",
            );
          }
          const payload = {
            category,
            currency: "PHP",
            occurred_at: new Date(values.occurred_at).toISOString(),
            amount: category === "FUEL" ? null : values.amount,
            liters: category === "FUEL" ? values.liters : null,
            price_per_liter:
              category === "FUEL" ? values.price_per_liter : null,
            odometer: category === "FUEL" ? values.odometer || null : null,
            description: values.description || null,
            vendor_name: values.vendor_name || null,
            reference_number: values.reference_number || null,
          };
          if (category === "OTHER" && values.description.trim().length < 3)
            throw new Error("Other requires an explanation.");
          for (const file of files) await validateFile(file, file.name);
          if (own) {
            await queueExpense(trip, payload, files);
            setMessage(
              "Saved locally. Check sync status for server confirmation.",
            );
            void sync().catch(() => {});
          } else {
            const body = {
              ...payload,
              expected_version: trip.version,
              ...(initial ? { reason: values.reason } : {}),
            };
            const fingerprint = JSON.stringify(body);
            if (
              !operation.current ||
              (!operation.current.result &&
                operation.current.body !== fingerprint)
            )
              operation.current = {
                body: fingerprint,
                key: crypto.randomUUID(),
                uploaded: 0,
                receiptKeys: files.map(() => crypto.randomUUID()),
              };
            const op = operation.current;
            if (!op.result)
              op.result = await post(
                initial
                  ? `/expenses/${initial.id}/correct`
                  : `/trips/${trip.id}/expenses`,
                body,
                op.key,
              );
            if (!op.result)
              throw new Error(
                "Expense response missing. Retry with the same action.",
              );
            const savedResult = op.result;
            setAccepted(true);
            for (let i = op.uploaded; i < files.length; i++) {
              const file = files[i];
              const r = await fetch(
                `/api/v1/expenses/${savedResult.expense.id}/evidence?${new URLSearchParams({ filename: file.name, expected_version: String(savedResult.trip_version) })}`,
                {
                  method: "POST",
                  headers: {
                    "Content-Type": file.type,
                    "Idempotency-Key": op.receiptKeys[i],
                  },
                  body: file,
                  credentials: "same-origin",
                },
              );
              const data = await r.json();
              if (!r.ok)
                throw new Error(
                  data?.error?.message ??
                    "Expense saved; receipt not confirmed. Retry to finish upload.",
                );
              savedResult.trip_version = data.result.trip_version;
              op.uploaded = i + 1;
            }
            setMessage("Expense and selected receipts saved.");
          }
          onDone();
        } catch (e) {
          setError(e instanceof Error ? e.message : "Unable to save expense.");
        } finally {
          setBusy(false);
        }
      }}
    >
      <h3>{initial ? "Correct expense" : "Add expense"}</h3>
      {error && <ErrorState message={error} />}{" "}
      {message && <p role="status">{message}</p>}
      <label>
        Expense category
        <select
          value={category}
          disabled={busy || accepted}
          onChange={(e) => setCategory(e.target.value)}
        >
          {categories.map((c) => (
            <option key={c} value={c}>
              {human(c)}
            </option>
          ))}
        </select>
      </label>
      <div className="form-grid">
        {(category === "FUEL"
          ? [
              ["liters", "Liters"],
              ["price_per_liter", "Price per liter (PHP)"],
              ["odometer", "Odometer (km, optional)"],
            ]
          : [["amount", "Amount (PHP)"]]
        ).map(([name, label]) => (
          <label key={name}>
            {label}
            <input
              inputMode="decimal"
              value={values[name]}
              required={name !== "odometer"}
              disabled={busy || accepted}
              onChange={(e) => setValues({ ...values, [name]: e.target.value })}
            />
          </label>
        ))}
        <label>
          Date and time
          <input
            type="datetime-local"
            required
            value={values.occurred_at}
            disabled={busy || accepted}
            onChange={(e) =>
              setValues({ ...values, occurred_at: e.target.value })
            }
          />
        </label>
        <label>
          {category === "FUEL" ? "Fuel station" : "Vendor / location / payee"}
          <input
            maxLength={160}
            required={category === "SUBCONTRACTOR"}
            value={values.vendor_name}
            disabled={busy || accepted}
            onChange={(e) =>
              setValues({ ...values, vendor_name: e.target.value })
            }
          />
        </label>
        <label>
          Receipt / reference number
          <input
            maxLength={120}
            value={values.reference_number}
            disabled={busy || accepted}
            onChange={(e) =>
              setValues({ ...values, reference_number: e.target.value })
            }
          />
        </label>
      </div>
      {category === "FUEL" && (
        <p>
          Estimated total: {estimate ? php(estimate) : "Enter liters and price"}
          . Server recalculates on submission.
        </p>
      )}
      <label>
        Expense notes
        <textarea
          maxLength={2000}
          required={category === "OTHER"}
          value={values.description}
          disabled={busy || accepted}
          onChange={(e) =>
            setValues({ ...values, description: e.target.value })
          }
        />
      </label>
      {initial && (
        <label>
          Correction reason
          <input
            required
            minLength={3}
            maxLength={2000}
            value={values.reason}
            disabled={busy}
            onChange={(e) => setValues({ ...values, reason: e.target.value })}
          />
        </label>
      )}
      <label>
        Receipts (optional, JPEG / PNG / WebP, up to 5 MiB each)
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          disabled={busy || accepted}
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
      </label>
      {files.map((f, i) => (
        <p className="small muted" key={i}>
          {f.name} · Selected locally; upload unconfirmed
        </p>
      ))}
      <button className="button primary" disabled={busy}>
        {busy
          ? "Saving expense and receipts…"
          : initial
            ? "Save correction"
            : "Save expense"}
      </button>
    </form>
  );
}
export function ExpensesPanel({
  trip,
  identity,
  own = false,
  onChanged,
}: {
  trip: TripRecord;
  identity: Identity;
  own?: boolean;
  onChanged: () => void;
}) {
  const [page, setPage] = useState<Page>(),
    [offset, setOffset] = useState(0),
    [revision, setRevision] = useState(0),
    [notice, setNotice] = useState(""),
    [error, setError] = useState(""),
    [adding, setAdding] = useState(false),
    [selected, setSelected] = useState<Detail>(),
    [correcting, setCorrecting] = useState(false),
    [action, setAction] = useState<"review" | "void" | null>(null),
    [notes, setNotes] = useState(""),
    [busy, setBusy] = useState(false);
  const key = useRef<{ body: string; key: string } | null>(null);
  const closed = ["SCHEDULED", "COMPLETED", "CANCELLED"].includes(
    trip.current_status,
  );
  useEffect(() => {
    let active = true;
    request<Page>(`/trips/${trip.id}/expenses?limit=20&offset=${offset}`)
      .then((data) => {
        if (active) {
          setPage(data);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [trip.id, trip.version, offset, revision]);
  useEffect(() => {
    if (!own) return;
    const update = () => setRevision((v) => v + 1);
    window.addEventListener("fleetpilot-sync", update);
    return () => window.removeEventListener("fleetpilot-sync", update);
  }, [own]);
  const done = () => {
    setNotice(
      own
        ? "Saved locally. Check sync status for server confirmation."
        : "Expense change saved successfully.",
    );
    setAdding(false);
    setSelected(undefined);
    setCorrecting(false);
    setRevision((v) => v + 1);
    onChanged();
  };
  return (
    <Card
      className={
        own
          ? "master-card expense-panel driver-task-card driver-expense-card"
          : "master-card expense-panel"
      }
      title="Trip expenses"
    >
      {notice && (
        <p role="status" className="success-banner">
          {notice}
        </p>
      )}
      <p className="small muted">
        Operational cost inputs in PHP, including advances. These totals are not
        accounting expense or profitability.
      </p>
      {error && (
        <>
          <ErrorState message={error} />
          <button
            className="button secondary"
            onClick={() => setRevision((v) => v + 1)}
          >
            Retry expenses
          </button>
        </>
      )}
      {!page && !error ? (
        <LoadingState />
      ) : (
        page && (
          <>
            <p>
              <strong>Total trip expenses: {php(page.submitted_total)}</strong>{" "}
              · Reviewed: {php(page.reviewed_total)}
            </p>
            {page.summary.map((s) => (
              <p className="small" key={s.category}>
                {human(s.category)}: {php(s.submitted_total)}
              </p>
            ))}
            {!page.items.length && (
              <p className="muted">No expenses recorded yet.</p>
            )}
            {page.items.map((item) => (
              <div className="assignment-current" key={item.id}>
                <strong>
                  {human(item.category)} · {php(item.amount)}
                </strong>
                <StatusBadge
                  tone={
                    item.status === "REVIEWED" && !item.administratively_voided
                      ? "active"
                      : "neutral"
                  }
                >
                  {item.administratively_voided
                    ? "Administratively voided"
                    : human(item.status)}
                </StatusBadge>
                <span>{dateLabel(item.occurred_at)}</span>
                <button
                  className="button secondary"
                  onClick={async () => {
                    try {
                      setSelected(
                        await request<Detail>(`/expenses/${item.id}`),
                      );
                      setCorrecting(false);
                      setAction(null);
                    } catch (e) {
                      setError(
                        e instanceof Error
                          ? e.message
                          : "Details unavailable offline.",
                      );
                    }
                  }}
                >
                  View expense
                </button>
              </div>
            ))}
            <div className="master-actions">
              <button
                className="button secondary"
                disabled={!offset}
                onClick={() => setOffset(offset - 20)}
              >
                Previous expenses
              </button>
              <button
                className="button secondary"
                disabled={offset + 20 >= page.total}
                onClick={() => setOffset(offset + 20)}
              >
                More expenses
              </button>
            </div>
          </>
        )
      )}
      {trip.current_status === "COMPLETED" &&
        !own &&
        can(identity, "closed_trip_adjustments.read") &&
        page && (
          <Adjustments
            tripId={trip.id}
            identity={identity}
            expenses={page.items}
            onChanged={done}
          />
        )}
      {!closed &&
        can(identity, own ? "driver_expense.create_own" : "expenses.create") &&
        !adding && (
          <button className="button primary" onClick={() => setAdding(true)}>
            Add expense
          </button>
        )}
      {adding && !closed && <ExpenseForm trip={trip} own={own} onDone={done} />}
      {selected && (
        <section className="audit-history">
          <h3>Expense history</h3>
          {trip.current_status === "COMPLETED" && selected.effective && (
            <p>
              Original submission: {php(selected.revisions[0].amount)} · Current
              effective value:{" "}
              {selected.effective.voided
                ? "Voided"
                : php(selected.effective.amount)}
            </p>
          )}
          <p>
            Submitted {dateLabel(selected.submitted_at)} · Actor{" "}
            {selected.submitted_by}
          </p>
          {selected.revisions.map((r) => (
            <p key={r.revision_number}>
              Revision {r.revision_number}: {human(r.category)} ·{" "}
              {php(r.amount)} · {r.description} · {dateLabel(r.created_at)} ·{" "}
              {r.created_by} {r.reason && `· ${r.reason}`}
            </p>
          ))}
          {selected.reviewed_at && (
            <p>
              Reviewed {dateLabel(selected.reviewed_at)} ·{" "}
              {selected.reviewed_by} · {selected.review_notes}
            </p>
          )}
          {selected.void_reason && <p>Void reason: {selected.void_reason}</p>}
          {selected.evidence.map((e) => (
            <div key={e.id}>
              <p>
                {e.original_filename} · {human(e.status)} ·{" "}
                {dateLabel(e.uploaded_at)} · {e.uploaded_by}
              </p>
              <Receipt id={e.id} name={e.original_filename} />
            </div>
          ))}
          {!own && !closed && (
            <div className="master-actions">
              {(["review", "correct", "void"] as const)
                .filter((a) => can(identity, `expenses.${a}`))
                .map((a) => (
                  <button
                    key={a}
                    className="button secondary"
                    onClick={() => {
                      setNotes("");
                      setCorrecting(a === "correct");
                      setAction(a === "correct" ? null : a);
                    }}
                  >
                    {human(a)} expense
                  </button>
                ))}
            </div>
          )}
          {correcting && !closed && (
            <ExpenseForm
              key={selected.id}
              trip={trip}
              own={false}
              initial={selected}
              onDone={done}
            />
          )}
          {action && !closed && (
            <form
              className="master-form"
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                setError("");
                try {
                  const body = {
                    expected_version: trip.version,
                    ...(action === "void" ? { reason: notes } : { notes }),
                  };
                  const value = JSON.stringify({
                    id: selected.id,
                    action,
                    body,
                  });
                  if (key.current?.body !== value)
                    key.current = { body: value, key: crypto.randomUUID() };
                  await post(
                    `/expenses/${selected.id}/${action}`,
                    body,
                    key.current.key,
                  );
                  setAction(null);
                  done();
                } catch (e) {
                  setError(
                    e instanceof Error ? e.message : "Unable to save review.",
                  );
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label>
                {action === "void"
                  ? "Void reason (history will be retained)"
                  : "Review notes"}
                <textarea
                  required={action === "void"}
                  minLength={action === "void" ? 3 : undefined}
                  maxLength={2000}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </label>
              <button className="button primary" disabled={busy}>
                Confirm {action}
              </button>
              <button
                type="button"
                className="button secondary"
                onClick={() => setAction(null)}
              >
                Cancel
              </button>
            </form>
          )}
        </section>
      )}
    </Card>
  );
}
export function FuelHistory({ vehicle }: { vehicle: string }) {
  const [page, setPage] = useState<Page>(),
    [offset, setOffset] = useState(0),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    request<Page>(`/vehicles/${vehicle}/fuel-history?limit=20&offset=${offset}`)
      .then((p) => {
        if (live) setPage(p);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [vehicle, offset]);
  return (
    <Card className="master-card" title="Vehicle fuel history">
      {error ? (
        <ErrorState message={error} />
      ) : !page ? (
        <LoadingState />
      ) : !page.total ? (
        <p>No fuel entries yet.</p>
      ) : (
        <>
          {page.items.map((r) => (
            <p key={r.id}>
              {dateLabel(r.occurred_at)} · {r.trip_number} · {r.first_name}{" "}
              {r.last_name} · {r.liters} L Ã— ₱{r.price_per_liter ?? "0"} ·{" "}
              {php(r.amount)} · {r.odometer ?? "Not captured"} km ·{" "}
              {r.administratively_voided
                ? "Administratively voided"
                : human(r.status)}
              {!!r.adjustment_sequence &&
                " · Adjusted effective cost; original fuel calculation retained"}
            </p>
          ))}
          <div className="master-actions">
            <button
              className="button secondary"
              disabled={!offset}
              onClick={() => setOffset(offset - 20)}
            >
              Previous fuel entries
            </button>
            <button
              className="button secondary"
              disabled={offset + 20 >= page.total}
              onClick={() => setOffset(offset + 20)}
            >
              More fuel entries
            </button>
          </div>
        </>
      )}
    </Card>
  );
}
