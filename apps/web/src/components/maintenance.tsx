"use client";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import {
  Card,
  ErrorState,
  LoadingState,
  StatusBadge,
  PageHeader,
} from "@fleetpilot/ui";
import { can } from "@fleetpilot/auth";
import type { Identity } from "@fleetpilot/types";
import { request } from "@/lib/client";
import { queueDefect, sync } from "@/lib/offline";
import { php } from "@/lib/money";
import { human, dateLabel } from "@/lib/trips";

type RecordData = {
  id: string;
  vehicle_id: string;
  kind?: string;
  title?: string;
  service_type?: string;
  status?: string;
  due_status?: string;
  next_due_odometer?: string;
  next_due_at?: string;
  description?: string;
  work_order_number?: string;
  version: number;
  total_cost?: string;
  severity?: string;
  category?: string;
  created_at?: string;
  work_performed?: string;
  downtime_started_at?: string;
  downtime_ended_at?: string;
  scheduled_at?: string;
  completed_at?: string;
  type?: string;
  priority?: string;
  maintenance_schedule_id?: string;
  defect_report_id?: string;
  odometer_at_open?: string;
  service_provider?: string;
  odometer_at_completion?: string;
  events?: {
    action: string;
    notes: string;
    created_at: string;
    actor_id: string;
  }[];
  cost_items?: {
    id: string;
    type: string;
    description: string;
    total_cost: string;
  }[];
  evidence?: { id: string; original_filename: string }[];
};
type History = {
  trusted_odometer: string;
  schedules: RecordData[];
  work_orders: RecordData[];
  defects: RecordData[];
};
const services = [
  "ENGINE_OIL",
  "OIL_FILTER",
  "AIR_FILTER",
  "FUEL_FILTER",
  "BRAKES",
  "TIRES",
  "TRANSMISSION",
  "COOLING_SYSTEM",
  "BATTERY",
  "GENERAL_INSPECTION",
  "REGISTRATION_RELATED_CHECK",
  "OTHER",
];
const pendingRequests = new Map<string, string>();
async function post<T>(path: string, body: unknown): Promise<T> {
  const requestId = path + JSON.stringify(body);
  const idempotencyKey = pendingRequests.get(requestId) ?? crypto.randomUUID();
  pendingRequests.set(requestId, idempotencyKey);
  const r = await fetch(`/api/v1${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(body),
    credentials: "same-origin",
  });
  const data = await r.json();
  if (!r.ok)
    throw new Error(
      data?.error?.message ?? "Unable to save maintenance record.",
    );
  pendingRequests.delete(requestId);
  return data;
}
function Input({
  name,
  label,
  type = "text",
  required = false,
  initial = "",
  minLength,
}: {
  name: string;
  label: string;
  type?: string;
  required?: boolean;
  initial?: string;
  minLength?: number;
}) {
  return (
    <label>
      {label}
      <input
        name={name}
        type={type}
        required={required}
        minLength={minLength}
        defaultValue={initial}
        step="any"
      />
    </label>
  );
}
function Select({
  name,
  label,
  values,
}: {
  name: string;
  label: string;
  values: string[];
}) {
  return (
    <label>
      {label}
      <select name={name}>
        {values.map((v) => (
          <option key={v} value={v}>
            {human(v)}
          </option>
        ))}
      </select>
    </label>
  );
}
function fields(e: FormEvent<HTMLFormElement>) {
  e.preventDefault();
  return Object.fromEntries(new FormData(e.currentTarget)) as Record<
    string,
    string
  >;
}
function message(e: unknown) {
  return e instanceof Error ? e.message : "Unable to save. Please retry.";
}
function Cards({
  items,
  work = false,
}: {
  items: RecordData[];
  work?: boolean;
}) {
  return (
    <>
      {!items.length && <p className="muted">No records yet.</p>}
      {items.map((r) => (
        <div className="trip-notice" key={r.id}>
          {work ? (
            <Link href={`/maintenance/work-orders/${r.id}`}>
              {r.work_order_number} · {r.title}
            </Link>
          ) : (
            <strong>
              {human(r.service_type ?? r.category ?? r.title ?? "")}
            </strong>
          )}{" "}
          <StatusBadge>{human(r.due_status ?? r.status ?? "OK")}</StatusBadge>
          {r.next_due_odometer && <p>Next service: {r.next_due_odometer} km</p>}
          {r.next_due_at && <p>Due date: {r.next_due_at}</p>}
          {r.description && <p>{r.description}</p>}
          {r.kind && (
            <Link
              href={
                r.kind === "WORK_ORDER"
                  ? `/maintenance/work-orders/${r.id}`
                  : `/fleet/vehicles/${r.vehicle_id}`
              }
            >
              Open record
            </Link>
          )}
          {r.total_cost && <p>Maintenance cost: {php(r.total_cost)}</p>}
          {r.completed_at && (
            <p>
              Service completed: {dateLabel(r.completed_at)} ·{" "}
              {r.odometer_at_completion} km
            </p>
          )}
        </div>
      ))}
    </>
  );
}
export function VehicleMaintenance({
  vehicle,
  identity,
}: {
  vehicle: string;
  identity: Identity;
}) {
  const [data, setData] = useState<History>(),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(""),
    [revision, setRevision] = useState(0),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    request<History>(`/vehicles/${vehicle}/maintenance`)
      .then((r) => {
        if (alive) setData(r);
      })
      .catch((e) => {
        if (alive) setError(message(e));
      });
    return () => {
      alive = false;
    };
  }, [vehicle, revision]);
  async function save(e: FormEvent<HTMLFormElement>, schedule: boolean) {
    const f = fields(e);
    setBusy(true);
    setError("");
    try {
      if (schedule) {
        const km = f.interval_type !== "DATE",
          days = f.interval_type !== "ODOMETER";
        await post(`/vehicles/${vehicle}/maintenance-schedules`, {
          service_type: f.service_type,
          interval_type: f.interval_type,
          odometer_interval_km: km ? Number(f.odometer_interval_km) : null,
          date_interval_days: days ? Number(f.date_interval_days) : null,
          last_service_odometer: km ? f.last_service_odometer : null,
          last_service_at: days ? f.last_service_at : null,
          warning_km: km ? Number(f.warning_km) : 0,
          warning_days: days ? Number(f.warning_days) : 0,
          notes: f.notes || null,
        });
      } else
        await post("/maintenance/work-orders", {
          vehicle_id: vehicle,
          type: f.type,
          priority: f.priority,
          title: f.title,
          description: f.description,
          requires_vehicle_downtime: f.downtime === "on",
          maintenance_schedule_id: f.schedule || null,
          service_provider: f.service_provider || null,
        });
      setSaved(
        schedule ? "Maintenance schedule created." : "Work order created.",
      );
      setRevision((v) => v + 1);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="master-card" title="Maintenance">
      <Link href="/maintenance">View maintenance list</Link>
      {error && <ErrorState message={error} />}
      <button
        className="button secondary"
        onClick={() => {
          setError("");
          setRevision((v) => v + 1);
        }}
      >
        Refresh maintenance
      </button>
      {saved && <p role="status">{saved}</p>}
      {!data && !error && <LoadingState />}
      {data && (
        <>
          <p>Trusted odometer: {data.trusted_odometer} km</p>
          <h3>Next service</h3>
          <Cards items={data.schedules} />
          <h3>Open work orders</h3>
          <Cards
            work
            items={data.work_orders.filter(
              (r) => !["COMPLETED", "CANCELLED"].includes(r.status ?? ""),
            )}
          />
          <h3>Service history</h3>
          <Cards
            work
            items={data.work_orders.filter((r) =>
              ["COMPLETED", "CANCELLED"].includes(r.status ?? ""),
            )}
          />
          <h3>Defect reports</h3>
          {data.defects.map((r) => (
            <DefectReview
              key={r.id}
              row={r}
              identity={identity}
              changed={() => setRevision((v) => v + 1)}
            />
          ))}
          {!data.defects.length && <p className="muted">No defect reports.</p>}
          {can(identity, "maintenance.schedule.create") && (
            <details>
              <summary>Create maintenance schedule</summary>
              <form className="master-form" onSubmit={(e) => save(e, true)}>
                <Select
                  name="service_type"
                  label="Service type"
                  values={services}
                />
                <Select
                  name="interval_type"
                  label="Interval"
                  values={["ODOMETER", "DATE", "ODOMETER_OR_DATE"]}
                />
                <Input
                  name="odometer_interval_km"
                  label="Every km"
                  type="number"
                />
                <Input
                  name="date_interval_days"
                  label="Every days"
                  type="number"
                />
                <Input
                  name="last_service_odometer"
                  label="Last service odometer"
                  type="number"
                />
                <Input
                  name="last_service_at"
                  label="Last service date"
                  type="date"
                />
                <Input
                  name="warning_km"
                  label="Warning km"
                  type="number"
                  initial="0"
                />
                <Input
                  name="warning_days"
                  label="Warning days"
                  type="number"
                  initial="0"
                />
                <Input name="notes" label="Service description / notes" />
                <button className="button primary" disabled={busy}>
                  Save schedule
                </button>
              </form>
            </details>
          )}
          {can(identity, "maintenance.work_order.create") && (
            <details>
              <summary>Create work order</summary>
              <form className="master-form" onSubmit={(e) => save(e, false)}>
                <Input name="title" label="Work order title" required />
                <Input name="description" label="Work description" required />
                <Select
                  name="type"
                  label="Work type"
                  values={["PREVENTIVE", "REPAIR", "INSPECTION", "OTHER"]}
                />
                <Select
                  name="priority"
                  label="Priority"
                  values={["NORMAL", "LOW", "HIGH", "CRITICAL"]}
                />
                <label>
                  Source schedule
                  <select name="schedule">
                    <option value="">None</option>
                    {data.schedules.map((s) => (
                      <option key={s.id} value={s.id}>
                        {human(s.service_type ?? "")}
                      </option>
                    ))}
                  </select>
                </label>
                <Input name="service_provider" label="Service provider" />
                <label>
                  <input type="checkbox" name="downtime" />
                  Requires vehicle downtime
                </label>
                <button className="button primary" disabled={busy}>
                  Save work order
                </button>
              </form>
            </details>
          )}
        </>
      )}
    </Card>
  );
}
function DefectReview({
  row,
  identity,
  changed,
}: {
  row: RecordData;
  identity: Identity;
  changed: () => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [detail, setDetail] = useState<RecordData>();
  async function act(e: FormEvent<HTMLFormElement>) {
    const f = fields(e);
    setBusy(true);
    try {
      if (f.action === "work") {
        await post("/maintenance/work-orders", {
          vehicle_id: row.vehicle_id,
          defect_report_id: row.id,
          type: "DEFECT_RESPONSE",
          priority: row.severity === "CRITICAL" ? "CRITICAL" : "HIGH",
          title: human(row.category ?? "Defect") + " repair",
          description: row.description,
          requires_vehicle_downtime: true,
        });
      } else await post(`/defects/${row.id}/${f.action}`, { reason: f.reason });
      changed();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="trip-notice">
      <strong>
        {human(row.severity ?? "")} · {human(row.category ?? "")}
      </strong>
      <StatusBadge>{human(row.status ?? "REPORTED")}</StatusBadge>
      <p>{row.description}</p>
      {error && <ErrorState message={error} />}
      <button
        className="button secondary"
        onClick={() =>
          request<RecordData>(`/defects/${row.id}`)
            .then(setDetail)
            .catch((e) => setError(message(e)))
        }
      >
        View defect evidence
      </button>
      {detail && <Evidence rows={detail.evidence ?? []} />}
      {can(identity, "defects.review") &&
        ["REPORTED", "REVIEWED"].includes(row.status ?? "") && (
          <form className="master-form" onSubmit={act}>
            <Select
              name="action"
              label="Defect action"
              values={
                row.status === "REVIEWED"
                  ? ["work", "dismiss"]
                  : ["review", "dismiss"]
              }
            />
            <Input name="reason" label="Review / dismissal reason" required />
            <button className="button secondary" disabled={busy}>
              Apply defect action
            </button>
          </form>
        )}
    </div>
  );
}
function Evidence({
  rows,
}: {
  rows: { id: string; original_filename: string }[];
}) {
  return (
    <>
      {rows.map((r) => (
        <a
          key={r.id}
          href={`/api/v1/maintenance-evidence/${r.id}`}
          target="_blank"
          rel="noreferrer"
        >
          {r.original_filename}
        </a>
      ))}
    </>
  );
}
export function MaintenanceList({ identity }: { identity: Identity }) {
  const [view, setView] = useState("attention"),
    [data, setData] = useState<{ items: RecordData[]; total: number }>(),
    [error, setError] = useState(""),
    [page, setPage] = useState(1),
    [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    let alive = true;
    request<{ items: RecordData[]; total: number }>(
      `/maintenance/${view === "upcoming" ? "attention" : view === "open" || view === "history" ? "work-orders" : view}?view=${view === "upcoming" ? "UPCOMING" : view === "attention" ? "NEEDS_ATTENTION" : view === "open" ? "OPEN" : view === "history" ? "HISTORY" : "ALL"}&page=${page}&search=${encodeURIComponent(query)}`,
    )
      .then((r) => {
        if (alive) setData(r);
      })
      .catch((e) => {
        if (alive) setError(message(e));
      });
    return () => {
      alive = false;
    };
  }, [view, page, query, revision]);
  return (
    <>
      <PageHeader
        title="Maintenance"
        description="Service schedules, repairs and vehicle issues."
      />
      <Link href="/fleet/vehicles">Back to vehicles</Link>
      <Card className="master-card">
        <form
          className="master-toolbar"
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setQuery(search);
          }}
        >
          <label>
            Maintenance view
            <select
              value={view}
              onChange={(e) => {
                setView(e.target.value);
                setPage(1);
                setData(undefined);
                setError("");
              }}
            >
              <option value="attention">Needs attention</option>
              <option value="upcoming">Upcoming</option>
              <option value="open">Open work orders</option>
              <option value="history">History</option>
              <option value="schedules">Service schedules</option>
              <option value="work-orders">Work orders and history</option>
              <option value="defects">Defect reports</option>
            </select>
          </label>
          <label>
            Search maintenance
            <input value={search} onChange={(e) => setSearch(e.target.value)} />
          </label>
          <button className="button secondary">Search</button>
        </form>
        {error && <ErrorState message={error} />}{" "}
        {!data && !error && <LoadingState />}
        {data && (
          <>
            {view === "defects" ? (
              data.items.map((r) => (
                <DefectReview
                  key={r.id}
                  row={r}
                  identity={identity}
                  changed={() => setRevision((r) => r + 1)}
                />
              ))
            ) : (
              <Cards
                items={data.items}
                work={["work-orders", "open", "history"].includes(view)}
              />
            )}
            <p>
              {data.total} records · Page {page}
            </p>
            <button
              className="button secondary"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <button
              className="button secondary"
              disabled={page * 20 >= data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </>
        )}
      </Card>
    </>
  );
}
export function WorkOrderDetail({
  id,
  identity,
}: {
  id: string;
  identity: Identity;
}) {
  const [data, setData] = useState<RecordData>(),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(""),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    request<RecordData>(`/maintenance/work-orders/${id}`)
      .then(setData)
      .catch((e) => setError(message(e)));
  }, [id, revision]);
  async function save(e: FormEvent<HTMLFormElement>, kind: string) {
    const f = fields(e);
    setError("");
    setBusy(true);
    try {
      if (kind === "cost")
        await post(`/maintenance/work-orders/${id}/cost-items`, {
          type: f.type,
          description: f.description,
          quantity: f.quantity,
          unit_cost: f.unit_cost,
          vendor: f.vendor || null,
          reference: f.reference || null,
        });
      else
        await post(`/maintenance/work-orders/${id}/${f.action}`, {
          expected_version: data?.version,
          scheduled_at: f.scheduled_at
            ? new Date(f.scheduled_at).toISOString()
            : null,
          odometer_at_completion: f.odometer || null,
          work_performed: f.work_performed || null,
          reason: f.reason || null,
        });
      setSaved("Maintenance record saved.");
      setRevision((r) => r + 1);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    try {
      const f = new FormData(e.currentTarget),
        file = f.get("file") as File;
      const digest = Array.from(
        new Uint8Array(
          await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
        ),
      )
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
      const uploadId = `${id}:${f.get("type")}:${file.name}:${digest}`;
      const uploadKey = pendingRequests.get(uploadId) ?? crypto.randomUUID();
      pendingRequests.set(uploadId, uploadKey);
      const r = await fetch(
        `/api/v1/maintenance/work-orders/${id}/evidence?filename=${encodeURIComponent(file.name)}&evidence_type=${f.get("type")}`,
        {
          method: "POST",
          headers: {
            "Content-Type": file.type,
            "Idempotency-Key": uploadKey,
          },
          body: file,
        },
      );
      if (!r.ok)
        throw new Error("Upload failed. Check image type/size and retry.");
      pendingRequests.delete(uploadId);
      setSaved("Evidence uploaded.");
      setRevision((r) => r + 1);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        title={data?.work_order_number ?? "Work order"}
        description={data?.title ?? "Maintenance details"}
      />
      <Link href="/maintenance">Back to maintenance</Link>
      {error && <ErrorState message={error} />}{" "}
      {saved && <p role="status">{saved}</p>}
      {!data && !error && <LoadingState />}
      {data && (
        <>
          <Card className="master-card" title="Work order">
            <StatusBadge>{human(data.status ?? "OPEN")}</StatusBadge>
            <p>
              {human(data.type ?? "")} · {human(data.priority ?? "")} priority
            </p>
            <p>{data.description}</p>
            <p>Scheduled: {dateLabel(data.scheduled_at)}</p>
            <p>Opened at odometer: {data.odometer_at_open ?? "Unavailable"}</p>
            <p>Source schedule: {data.maintenance_schedule_id ?? "None"}</p>
            <p>Source defect: {data.defect_report_id ?? "None"}</p>
            <Link href={`/fleet/vehicles/${data.vehicle_id}`}>
              Vehicle record
            </Link>
            <p>Provider: {data.service_provider ?? "Not specified"}</p>
            <p>Maintenance cost: {php(data.total_cost ?? "0")}</p>
            <p>
              Completion odometer:{" "}
              {data.odometer_at_completion ?? "Not completed"}
            </p>
            <p>{data.work_performed}</p>
            <p>
              Downtime: {dateLabel(data.downtime_started_at)} —{" "}
              {dateLabel(data.downtime_ended_at)}
            </p>
            {!["COMPLETED", "CANCELLED"].includes(data.status ?? "") &&
              can(
                identity,
                data.status === "IN_PROGRESS"
                  ? "maintenance.work_order.complete"
                  : "maintenance.work_order.update",
              ) && (
                <form
                  className="master-form"
                  onSubmit={(e) => save(e, "action")}
                >
                  <Select
                    name="action"
                    label="Work order action"
                    values={
                      data.status === "IN_PROGRESS"
                        ? ["complete"]
                        : data.status === "SCHEDULED"
                          ? ["start", "cancel"]
                          : ["schedule", "start", "cancel"]
                    }
                  />
                  <Input
                    name="scheduled_at"
                    label="Scheduled time"
                    type="datetime-local"
                  />
                  <Input
                    name="odometer"
                    label="Completion odometer"
                    type="number"
                  />
                  <Input name="work_performed" label="Work performed" />
                  <Input name="reason" label="Cancellation reason" />
                  <button className="button primary" disabled={busy}>
                    Apply work order action
                  </button>
                </form>
              )}
          </Card>
          <Card className="master-card" title="Maintenance costs">
            {data.cost_items?.map((c) => (
              <p key={c.id}>
                {human(c.type)} · {c.description} · {php(c.total_cost)}
              </p>
            ))}
            {!["COMPLETED", "CANCELLED"].includes(data.status ?? "") &&
              can(identity, "maintenance.cost.manage") && (
                <form className="master-form" onSubmit={(e) => save(e, "cost")}>
                  <Select
                    name="type"
                    label="Cost type"
                    values={["PART", "LABOR", "OTHER"]}
                  />
                  <Input name="description" label="Cost description" required />
                  <Input
                    name="quantity"
                    label="Quantity"
                    initial="1"
                    required
                  />
                  <Input name="unit_cost" label="Unit cost PHP" required />
                  <Input name="vendor" label="Vendor" />
                  <Input name="reference" label="Reference" />
                  <button className="button primary" disabled={busy}>
                    Add maintenance cost
                  </button>
                </form>
              )}
          </Card>
          <Card className="master-card" title="Maintenance evidence">
            <Evidence rows={data.evidence ?? []} />
            {!["COMPLETED", "CANCELLED"].includes(data.status ?? "") &&
              can(identity, "maintenance.evidence.upload") && (
                <form className="master-form" onSubmit={upload}>
                  <Select
                    name="type"
                    label="Evidence type"
                    values={[
                      "MAINTENANCE_RECEIPT",
                      "SERVICE_INVOICE",
                      "MAINTENANCE_BEFORE_PHOTO",
                      "MAINTENANCE_AFTER_PHOTO",
                    ]}
                  />
                  <Input
                    name="file"
                    label="Evidence image"
                    type="file"
                    required
                  />
                  <button className="button secondary" disabled={busy}>
                    {busy ? "Saving…" : "Upload evidence"}
                  </button>
                </form>
              )}
          </Card>
          <Card className="master-card" title="Maintenance timeline">
            {data.events?.map((r, i) => (
              <p key={i}>
                {human(r.action.replaceAll(".", " "))} ·{" "}
                {dateLabel(r.created_at)} · {r.notes} · Actor {r.actor_id}
              </p>
            ))}
          </Card>
        </>
      )}
    </>
  );
}
export function DriverDefect({
  vehicle,
  trip,
}: {
  vehicle?: string;
  trip?: string;
}) {
  const [open, setOpen] = useState(false),
    [vehicles, setVehicles] = useState<{ id: string; unit_number: string }[]>(
      [],
    ),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    request<{ items: { id: string; unit_number: string }[] }>(
      "/driver/maintenance-vehicles",
    )
      .then((r) => setVehicles(r.items))
      .catch((e) => setError(message(e)));
  }, []);
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = e.currentTarget,
      f = new FormData(form);
    try {
      await queueDefect(
        vehicle ?? String(f.get("vehicle")),
        {
          severity: f.get("severity"),
          category: f.get("category"),
          description: f.get("description"),
        },
        f
          .getAll("photos")
          .filter((v) => v instanceof File && v.size > 0) as File[],
        trip,
      );
      setSaved("Saved locally. Check sync status for server confirmation.");
      form.reset();
      void sync().catch(() => {});
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="master-card" title="Vehicle issue">
      <button className="button secondary" onClick={() => setOpen((v) => !v)}>
        Report vehicle issue
      </button>
      {saved && <p role="status">{saved}</p>}
      {open && (
        <>
          {error && <ErrorState message={error} />}
          <form className="master-form" onSubmit={save}>
            {!vehicle && (
              <label>
                Assigned vehicle
                <select name="vehicle" required>
                  <option value="">Select vehicle</option>
                  {vehicles.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.unit_number}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <Select
              name="severity"
              label="Severity"
              values={["MINOR", "MODERATE", "SERIOUS", "CRITICAL"]}
            />
            <Select
              name="category"
              label="Defect category"
              values={[
                "ENGINE",
                "BRAKES",
                "TIRES",
                "ELECTRICAL",
                "LIGHTS",
                "SUSPENSION",
                "STEERING",
                "COOLING",
                "TRANSMISSION",
                "BODY",
                "SAFETY_EQUIPMENT",
                "OTHER",
              ]}
            />
            <Input
              name="description"
              label="Defect description"
              required
              minLength={3}
            />
            <label>
              Defect photos
              <input
                name="photos"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
              />
            </label>
            <button className="button primary" disabled={busy}>
              {busy ? "Saving…" : "Save vehicle issue"}
            </button>
          </form>
        </>
      )}
    </Card>
  );
}
