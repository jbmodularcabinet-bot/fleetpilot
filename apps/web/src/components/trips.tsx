"use client";
import { FinancialPanel } from "./financials";
import { DriverDefect } from "./maintenance";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, MapPin, Plus, Truck } from "lucide-react";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
  DriverPrimaryAction,
} from "@fleetpilot/ui";
import { can, isClientDemo } from "@fleetpilot/auth";
import type { Identity } from "@fleetpilot/types";
import { queueTransition, sync } from "@/lib/offline";
import { request } from "@/lib/client";
import { useHydrated } from "@/lib/hydrated";
import { DeliveryPanel } from "./delivery";
import { ExpensesPanel } from "./expenses";
import {
  config,
  recordName,
  type Domain,
  type MasterRecord,
  type Page,
} from "@/lib/master-data";
import {
  dateLabel,
  human,
  localInput,
  tripFields,
  tripPayload,
  tripStatuses,
  type TripRecord,
  type Milestone,
} from "@/lib/trips";

function useLoad<T>(path: string, revision = 0): { data?: T; error?: string } {
  const [syncRevision, setSyncRevision] = useState(0);
  useEffect(() => {
    if (!window.location.pathname.startsWith("/driver")) return;
    const refresh = () => setSyncRevision((v) => v + 1);
    window.addEventListener("fleetpilot-sync", refresh);
    return () => window.removeEventListener("fleetpilot-sync", refresh);
  }, []);
  const [result, setResult] = useState<{
    path: string;
    revision: number;
    data?: T;
    error?: string;
  }>();
  useEffect(() => {
    let alive = true;
    request<T>(path)
      .then((data) => {
        if (alive) setResult({ path, revision, data });
      })
      .catch((err) => {
        if (alive)
          setResult({
            path,
            revision,
            error: err instanceof Error ? err.message : "Unable to load trips.",
          });
      });
    return () => {
      alive = false;
    };
  }, [path, revision, syncRevision]);
  // Keep mounted form state while refreshing the same resource after sync.
  return result?.path === path ? result : {};
}
function TripBadge({ value }: { value: string }) {
  return (
    <StatusBadge
      tone={
        value === "COMPLETED" || value === "DELIVERED"
          ? "positive"
          : value === "CANCELLED"
            ? "warning"
            : "active"
      }
    >
      {human(value)}
    </StatusBadge>
  );
}
function Pagination({
  data,
  offset,
  onChange,
}: {
  data: Page<unknown>;
  offset: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="master-pager">
      <span className="small muted">
        {data.total
          ? `${offset + 1}–${Math.min(offset + data.limit, data.total)} of ${data.total}`
          : "0 trips"}
      </span>
      <div>
        <button
          className="button secondary"
          disabled={!offset}
          onClick={() => onChange(Math.max(0, offset - data.limit))}
        >
          Previous
        </button>
        <button
          className="button secondary"
          disabled={offset + data.limit >= data.total}
          onClick={() => onChange(offset + data.limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
function ResourcePicker({
  domain,
  label,
  value,
  onChange,
  required = false,
  eligibleOnly = false,
}: {
  domain: Domain;
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  eligibleOnly?: boolean;
}) {
  const [query, setQuery] = useState("");
  const { data, error } = useLoad<Page<MasterRecord>>(
    `/${domain}?limit=100&search=${encodeURIComponent(query)}${eligibleOnly && domain !== "vehicles" ? "&status=ACTIVE" : ""}`,
  );
  const rows =
    data?.items.filter((row) => !eligibleOnly || row.status !== "INACTIVE") ??
    [];
  return (
    <div className="trip-picker">
      <label>
        Find {label.toLowerCase()}
        <input
          value={query}
          maxLength={160}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${config[domain].title.toLowerCase()}`}
        />
      </label>
      <label>
        {label}
        {required ? " *" : ""}
        <select
          aria-label={label}
          value={value}
          required={required}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">
            {required ? "Select a record" : "Not selected"}
          </option>
          {value && !rows.some((row) => row.id === value) && (
            <option value={value}>Selected record</option>
          )}
          {rows.map((row) => (
            <option key={row.id} value={row.id}>
              {recordName(domain, row)}
              {domain === "vehicles" ? ` · ${row.plate_number}` : ""}
            </option>
          ))}
        </select>
      </label>
      {error && <ErrorState message={error} />}{" "}
      {!data && !error && <span className="small muted">Loading choices…</span>}
      {data && data.total > 100 && (
        <span className="small muted">
          Refine your search to see more matches.
        </span>
      )}
    </div>
  );
}

export function DispatchBoard({ identity }: { identity: Identity }) {
  const [view, setView] = useState("today"),
    [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [driver, setDriver] = useState(""),
    [vehicle, setVehicle] = useState(""),
    [customer, setCustomer] = useState(""),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [sort, setSort] = useState("scheduled_pickup_at"),
    [direction, setDirection] = useState("asc");
  const [offset, setOffset] = useState(0),
    [revision, setRevision] = useState(0);
  const hydrated = useHydrated();
  const params = new URLSearchParams({
    view,
    search: query,
    sort,
    direction,
    limit: "20",
    offset: String(offset),
    ...(status ? { status } : {}),
    ...(driver ? { driver_id: driver } : {}),
    ...(vehicle ? { vehicle_id: vehicle } : {}),
    ...(customer ? { customer_id: customer } : {}),
    ...(from ? { date_from: from } : {}),
    ...(to ? { date_to: to } : {}),
  });
  const { data, error } = useLoad<Page<TripRecord>>(
    `/dispatch?${params}`,
    revision,
  );
  return (
    <div className="operations-workspace">
      <PageHeader
        title="Operations"
        description="Dispatch from verified trip records. Live location appears only when connected telemetry is available."
      >
        {can(identity, "trips.create") && (
          <Link className="button primary" href="/trips/new">
            <Plus size={17} />
            Create trip
          </Link>
        )}
      </PageHeader>
      <section
        className="operations-visibility"
        aria-labelledby="live-fleet-heading"
      >
        <div className="operations-visibility-copy">
          <span className="eyebrow">LIVE FLEET</span>
          <div className="operations-visibility-title">
            <span className="icon-box icon-box-active">
              <MapPin size={19} />
            </span>
            <div>
              <h2 id="live-fleet-heading">Location visibility</h2>
              <p>
                Live GPS telemetry is not connected in this release. FleetPilot
                does not infer truck positions from dispatch records.
              </p>
            </div>
          </div>
          <div className="operations-visibility-status">
            <StatusBadge>Telemetry not connected</StatusBadge>
            <span className="small muted">
              Dispatch and trip history remain the verified operational source.
            </span>
          </div>
        </div>
        <div
          className="operations-map-empty"
          role="img"
          aria-label="Live fleet map unavailable until verified GPS telemetry is connected"
        >
          <div className="operations-map-grid" aria-hidden="true" />
          <div className="operations-map-message">
            <MapPin size={26} />
            <strong>No fabricated truck positions</strong>
            <span>
              Connect validated location telemetry before showing live vehicles
              or route movement.
            </span>
          </div>
        </div>
      </section>
      <div className="operations-section-heading">
        <div>
          <span className="eyebrow">DISPATCH</span>
          <h2>Dispatch Board</h2>
          <p>Plan assigned work, schedules, drivers and trip status.</p>
        </div>
        {can(identity, "trip_profitability.read") && (
          <Link className="button secondary" href="/trips/profitability">
            View trip contribution
          </Link>
        )}
      </div>
      <nav className="trip-views" aria-label="Dispatch views">
        {[
          ["today", "Today"],
          ["upcoming", "Upcoming"],
          ["active", "Active"],
          ["closed", "Delivered / Completed"],
          ["cancelled", "Cancelled"],
          ["all", "All trips"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={view === key ? "selected" : ""}
            disabled={!hydrated}
            aria-pressed={view === key}
            onClick={() => {
              setView(key);
              setOffset(0);
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      <Card className="master-card dispatch-card">
        <form
          className="master-toolbar"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(search);
            setOffset(0);
          }}
        >
          <label className="master-search">
            Search trips
            <input
              value={search}
              disabled={!hydrated}
              maxLength={160}
              placeholder="Trip number, customer, location or reference"
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <button className="button secondary" disabled={!hydrated}>
            Search
          </button>
          <label>
            Status
            <select
              aria-label="Status"
              disabled={!hydrated}
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All statuses</option>
              {tripStatuses.map((value) => (
                <option value={value} key={value}>
                  {human(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Sort by
            <select
              value={sort}
              disabled={!hydrated}
              onChange={(e) => {
                setSort(e.target.value);
                setOffset(0);
              }}
            >
              {[
                "scheduled_pickup_at",
                "scheduled_delivery_at",
                "trip_number",
                "current_status",
                "created_at",
              ].map((value) => (
                <option key={value} value={value}>
                  {human(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Order
            <select
              value={direction}
              disabled={!hydrated}
              onChange={(e) => {
                setDirection(e.target.value);
                setOffset(0);
              }}
            >
              <option value="asc">Ascending</option>
              <option value="desc">Descending</option>
            </select>
          </label>
        </form>
        <details className="trip-filter-details">
          <summary>Customer, vehicle, driver & date filters</summary>
          <div className="form-grid">
            <ResourcePicker
              domain="customers"
              label="Customer filter"
              value={customer}
              onChange={(v) => {
                setCustomer(v);
                setOffset(0);
              }}
            />
            <ResourcePicker
              domain="vehicles"
              label="Vehicle filter"
              value={vehicle}
              onChange={(v) => {
                setVehicle(v);
                setOffset(0);
              }}
            />
            <ResourcePicker
              domain="drivers"
              label="Driver filter"
              value={driver}
              onChange={(v) => {
                setDriver(v);
                setOffset(0);
              }}
            />
            <div className="trip-picker">
              <label>
                From date
                <input
                  type="date"
                  value={from}
                  onChange={(e) => {
                    setFrom(e.target.value);
                    setOffset(0);
                  }}
                />
              </label>
              <label>
                Through date
                <input
                  type="date"
                  value={to}
                  onChange={(e) => {
                    setTo(e.target.value);
                    setOffset(0);
                  }}
                />
              </label>
            </div>
          </div>
          <p className="field-help">
            Date filters use {identity.organization.timezone}. Displayed times
            use your device timezone.
          </p>
        </details>
        {error ? (
          <>
            <ErrorState message={error} />
            <button
              className="button secondary"
              onClick={() => setRevision(revision + 1)}
            >
              Retry
            </button>
          </>
        ) : !data ? (
          <LoadingState />
        ) : !data.total ? (
          <EmptyState
            title="No trips in this view"
            description="Choose another view or create your first trip."
            icon={<Truck />}
          />
        ) : (
          <div className="table-scroll dispatch-table-wrap">
            <table className="dispatch-table">
              <caption className="sr-only">Dispatch trips</caption>
              <thead>
                <tr>
                  {[
                    "Trip / customer",
                    "Pickup → delivery",
                    "Scheduled pickup",
                    "Vehicle / driver",
                    "Status",
                    "Details",
                  ].map((title) => (
                    <th key={title} scope="col">
                      {title}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((trip) => (
                  <tr key={trip.id}>
                    <td>
                      <Link className="record-link" href={`/trips/${trip.id}`}>
                        {trip.trip_number}
                      </Link>
                      <small>{trip.customer_name}</small>
                    </td>
                    <td>
                      {trip.pickup_name} → {trip.delivery_name}
                    </td>
                    <td>{dateLabel(trip.scheduled_pickup_at)}</td>
                    <td>
                      {trip.vehicle_unit ?? "Unassigned"}
                      <small>{trip.driver_name ?? "No driver"}</small>
                    </td>
                    <td>
                      <TripBadge value={trip.current_status} />
                    </td>
                    <td>
                      <Link
                        className="record-link"
                        href={`/trips/${trip.id}`}
                        aria-label={`View ${trip.trip_number}`}
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && (
          <Pagination data={data} offset={offset} onChange={setOffset} />
        )}
      </Card>
    </div>
  );
}

export function TripEditor({ id }: { id?: string }) {
  const { data, error } = useLoad<TripRecord>(id ? `/trips/${id}` : "/me");
  if (error) return <ErrorState message={error} />;
  if (!data) return <LoadingState />;
  if (id && data.current_status !== "SCHEDULED")
    return (
      <ErrorState message="Operational fields are read-only after dispatch." />
    );
  return <TripForm key={id ?? "new"} initial={id ? data : undefined} />;
}
function TripForm({ initial }: { initial?: TripRecord }) {
  const router = useRouter(),
    hydrated = useHydrated();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      tripFields.map((field) => [
        field.key,
        field.type === "datetime-local"
          ? localInput(initial?.[field.key])
          : String(initial?.[field.key] ?? ""),
      ]),
    ),
  );
  const [customer, setCustomer] = useState(initial?.customer_id ?? ""),
    [vehicle, setVehicle] = useState(initial?.vehicle_id ?? ""),
    [driver, setDriver] = useState(initial?.driver_id ?? ""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <>
      <Link
        className="master-back"
        href={initial ? `/trips/${initial.id}` : "/dispatch"}
      >
        <ArrowLeft size={16} />
        Back to {initial ? "trip" : "dispatch"}
      </Link>
      <PageHeader
        title={initial ? "Edit trip" : "Create trip"}
        description="Schedule a delivery with clear stops, instructions and responsibility."
      />
      <Card className="master-card">
        <form
          method="post"
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            if (Boolean(vehicle) !== Boolean(driver)) {
              setError(
                "Choose both a vehicle and driver, or leave both unassigned.",
              );
              return;
            }
            if (
              values.scheduled_delivery_at &&
              new Date(values.scheduled_delivery_at) <=
                new Date(values.scheduled_pickup_at)
            ) {
              setError("Scheduled delivery must be after pickup.");
              return;
            }
            if (
              Boolean(values.cargo_weight) !== Boolean(values.cargo_weight_unit)
            ) {
              setError("Enter both cargo weight and its unit.");
              return;
            }
            setBusy(true);
            try {
              const payload = {
                ...tripPayload(values),
                customer_id: customer,
                ...(initial
                  ? { expected_version: initial.version }
                  : { vehicle_id: vehicle || null, driver_id: driver || null }),
              };
              const saved = await request<TripRecord>(
                `/trips${initial ? `/${initial.id}` : ""}`,
                initial ? "PATCH" : "POST",
                payload,
              );
              router.push(`/trips/${saved.id}?saved=1`);
              router.refresh();
            } catch (err) {
              setError(
                err instanceof Error ? err.message : "Unable to save trip.",
              );
              setBusy(false);
            }
          }}
        >
          <p className="small muted master-help">
            Fields marked * are required. Trip numbers are generated
            automatically. Times use your device timezone.
          </p>
          <fieldset disabled={!hydrated || busy}>
            <ResourcePicker
              domain="customers"
              label="Customer"
              value={customer}
              onChange={setCustomer}
              required
              eligibleOnly
            />
            <div className="form-grid trip-form-fields">
              {tripFields.map((field) => (
                <label key={field.key}>
                  {field.label}
                  {field.required ? " *" : ""}
                  {field.options ? (
                    <select
                      aria-label={field.label}
                      value={values[field.key]}
                      onChange={(e) =>
                        setValues({ ...values, [field.key]: e.target.value })
                      }
                    >
                      <option value="">Not specified</option>
                      {field.options.map((value) => (
                        <option key={value}>{value}</option>
                      ))}
                    </select>
                  ) : field.type === "textarea" ? (
                    <textarea
                      required={field.required}
                      minLength={field.required ? 2 : undefined}
                      maxLength={field.max}
                      rows={3}
                      value={values[field.key]}
                      onChange={(e) =>
                        setValues({ ...values, [field.key]: e.target.value })
                      }
                    />
                  ) : (
                    <input
                      type={field.type ?? "text"}
                      required={field.required}
                      minLength={
                        field.required && field.type !== "datetime-local"
                          ? 2
                          : undefined
                      }
                      maxLength={
                        field.type !== "number" ? field.max : undefined
                      }
                      min={field.min}
                      max={field.type === "number" ? field.max : undefined}
                      step={field.step}
                      value={values[field.key]}
                      onChange={(e) =>
                        setValues({ ...values, [field.key]: e.target.value })
                      }
                    />
                  )}
                </label>
              ))}
            </div>
            {!initial && (
              <>
                <h2 className="history-title">Optional trip assignment</h2>
                <div className="form-grid">
                  <ResourcePicker
                    domain="vehicles"
                    label="Vehicle"
                    value={vehicle}
                    onChange={setVehicle}
                    eligibleOnly
                  />
                  <ResourcePicker
                    domain="drivers"
                    label="Driver"
                    value={driver}
                    onChange={setDriver}
                    eligibleOnly
                  />
                </div>
                <p className="field-help">
                  Without a delivery time, the schedule reserves 24 hours from
                  pickup. Conflicting reservations are blocked.
                </p>
              </>
            )}
          </fieldset>
          {error && <ErrorState message={error} />}
          <div className="form-actions">
            <Link
              className="button secondary"
              href={initial ? `/trips/${initial.id}` : "/dispatch"}
            >
              Cancel
            </Link>
            <button className="button primary" disabled={!hydrated || busy}>
              {busy ? "Saving…" : "Save trip"}
            </button>
          </div>
        </form>
      </Card>
    </>
  );
}

export function TripDetail({
  id,
  identity,
  own = false,
  saved = false,
}: {
  id: string;
  identity: Identity;
  own?: boolean;
  saved?: boolean;
}) {
  const [revision, setRevision] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState(saved ? "Trip saved successfully." : "");
  const prefix = own ? "/driver/trips" : "/trips";
  const { data: trip, error: loadError } = useLoad<TripRecord>(
    `${prefix}/${id}`,
    revision,
  );
  const { data: timeline, error: timelineError } = useLoad<Milestone[]>(
    `${prefix}/${id}/milestones`,
    revision,
  );
  const [reason, setReason] = useState(""),
    [reviewed, setReviewed] = useState(false),
    [notes, setNotes] = useState("");
  async function mutate(suffix: string, body: object, method = "POST") {
    setBusy(true);
    setError("");
    try {
      if (own && suffix === "transition" && trip) {
        await queueTransition(trip, (body as { action: string }).action);
        setMessage("Saved locally. Waiting for server confirmation.");
        await sync();
      } else
        await request(`${prefix}/${id}/${suffix}`, method, {
          ...body,
          expected_version: trip?.version,
        });
      if (!own) setMessage("Trip updated successfully.");
      setRevision(revision + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update trip.");
    } finally {
      setBusy(false);
    }
  }
  if (loadError)
    return (
      <>
        <ErrorState message={loadError} />
        <Link href={own ? "/driver/trips" : "/dispatch"}>Back to trips</Link>
      </>
    );
  if (!trip) return <LoadingState />;
  const closed = ["COMPLETED", "CANCELLED"].includes(trip.current_status);
  return (
    <div className={own ? "driver-content" : "trip-command-workspace"}>
      <Link className="master-back" href={own ? "/driver/trips" : "/dispatch"}>
        <ArrowLeft size={16} />
        Back to {own ? "your trips" : "dispatch"}
      </Link>
      <PageHeader
        title={trip.trip_number}
        description={`${trip.pickup_name} → ${trip.delivery_name}`}
      >
        <div className="master-actions">
          <TripBadge value={trip.current_status} />
          {!own &&
            trip.current_status === "SCHEDULED" &&
            can(identity, "trips.update") && (
              <Link className="button secondary" href={`/trips/${id}/edit`}>
                Edit trip
              </Link>
            )}
        </div>
      </PageHeader>
      {!own && (
        <>
          <section className="trip-command-summary" aria-label="Trip route summary">
            <div className="trip-command-route">
              <span className="eyebrow">ROUTE</span>
              <strong>
                <span>{trip.pickup_name}</span>
                <ArrowRight size={18} aria-hidden="true" />
                <span>{trip.delivery_name}</span>
              </strong>
              <small>Scheduled pickup · {dateLabel(trip.scheduled_pickup_at)}</small>
            </div>
            <div className="trip-command-facts">
              <div>
                <span>Customer</span>
                <strong>{trip.customer_name}</strong>
              </div>
              <div>
                <span>Vehicle</span>
                <strong>{trip.vehicle_unit ?? "Unassigned"}</strong>
              </div>
              <div>
                <span>Driver</span>
                <strong>{trip.driver_name ?? "No driver"}</strong>
              </div>
            </div>
          </section>
          <nav className="trip-section-nav" aria-label="Trip sections">
            <a href="#trip-overview">Overview</a>
            <a href="#trip-tracking">Tracking</a>
            {can(identity, "expenses.read") && <a href="#trip-expenses">Expenses</a>}
            {can(identity, "pod.read") && <a href="#trip-pod">POD</a>}
            {can(identity, "trip_financials.read") &&
              can(identity, "trip_profitability.read") && (
                <a href="#trip-financial">Financial</a>
              )}
            {(!isClientDemo(identity) || can(identity, "audit.read")) && (
              <a href="#trip-activity">Activity</a>
            )}
          </nav>
        </>
      )}
      {message && (
        <p role="status" className="success-message">
          {message}
        </p>
      )}
      {error && (
        <>
          <ErrorState message={error} />
          <button
            className="button secondary"
            onClick={() => {
              setError("");
              setRevision(revision + 1);
            }}
          >
            Refresh trip
          </button>
        </>
      )}
      {own && trip.offline_pending && (
        <p role="status" className="trip-notice">
          Saved locally. The status badge shows the last server-confirmed state.
        </p>
      )}
      {own &&
        !closed &&
        can(identity, "driver_defect.create_own") &&
        trip.vehicle_id && (
          <DriverDefect vehicle={trip.vehicle_id} trip={trip.id} />
        )}
      {closed && (
        <p className="trip-notice">
          {trip.current_status === "COMPLETED"
            ? "Trip completed. Operational details are read-only."
            : "Trip cancelled. It cannot be resumed."}
        </p>
      )}
      {own && can(identity, "driver_pod.read_own") && (
        <DeliveryPanel
          trip={trip}
          identity={identity}
          own={own}
          onChanged={() => {
            setMessage(
              "Saved work retained. Check sync status for server confirmation.",
            );
            setRevision((value) => value + 1);
          }}
        />
      )}
      <section
        id={own ? undefined : "trip-overview"}
        className={own ? undefined : "trip-section"}
      >
        <div className="trip-detail-grid">
        <Card className="master-card" title="Trip details">
          <dl className="master-fields">
            <div>
              <dt>Customer</dt>
              <dd>{trip.customer_name}</dd>
            </div>
            <div>
              <dt>Vehicle / driver</dt>
              <dd>
                {trip.vehicle_unit ?? "Unassigned"} ·{" "}
                {trip.driver_name ?? "No driver"}
              </dd>
            </div>
            {tripFields
              .filter(
                (field) =>
                  !own ||
                  ![
                    "dispatcher_notes",
                    "customer_reference",
                    "reference_number",
                    "pickup_latitude",
                    "pickup_longitude",
                    "delivery_latitude",
                    "delivery_longitude",
                  ].includes(field.key),
              )
              .map((field) => (
                <div key={field.key}>
                  <dt>{field.label}</dt>
                  <dd>
                    {field.type === "datetime-local"
                      ? dateLabel(trip[field.key])
                      : (trip[field.key] ?? "Not specified")}
                  </dd>
                </div>
              ))}
            {!own && (
              <>
                <div>
                  <dt>Created</dt>
                  <dd>{dateLabel(trip.created_at)}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{dateLabel(trip.updated_at)}</dd>
                </div>
                <div>
                  <dt>Created by</dt>
                  <dd>{trip.created_by}</dd>
                </div>
              </>
            )}
            {trip.completed_at && (
              <div>
                <dt>Completed at</dt>
                <dd>{dateLabel(trip.completed_at)}</dd>
              </div>
            )}
            {!own && trip.cancelled_at && (
              <>
                <div>
                  <dt>Cancelled at</dt>
                  <dd>{dateLabel(trip.cancelled_at)}</dd>
                </div>
                <div>
                  <dt>Cancellation reason</dt>
                  <dd>{trip.cancellation_reason}</dd>
                </div>
              </>
            )}
          </dl>
        </Card>
        <div className="trip-side">
          <Card title="Next action" className="master-card">
            {trip.next_action &&
            can(
              identity,
              own ? "driver_trip.transition_own" : "trips.transition",
            ) ? (
              <>
                <p className="small muted">
                  Current milestone: {human(trip.current_milestone)}
                </p>
                <button
                  className="button primary driver-cta"
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        `${trip.next_action_label}? Confirm this milestone has occurred.`,
                      )
                    )
                      void mutate("transition", { action: trip.next_action });
                  }}
                >
                  {busy ? "Saving…" : trip.next_action_label}
                  <ArrowRight size={17} />
                </button>
              </>
            ) : (
              <p className="small muted">
                {closed
                  ? "No further actions."
                  : trip.current_status === "DELIVERED"
                    ? "Delivery confirmed. Awaiting operator closeout."
                    : trip.current_milestone === "UNLOADING_COMPLETED"
                      ? "Complete the delivery evidence workflow above."
                      : !trip.vehicle_unit
                        ? "Assign a vehicle and driver before dispatch."
                        : "Awaiting an authorized operator."}
              </p>
            )}
            {!own &&
              trip.current_status === "DELIVERED" &&
              can(identity, "trips.complete") && (
                <div className="assignment-form">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={reviewed}
                      onChange={(e) => setReviewed(e.target.checked)}
                    />
                    I reviewed the required trip details and milestone history.
                  </label>
                  <button
                    className="button primary"
                    disabled={
                      !reviewed ||
                      busy ||
                      (trip.pod_required && trip.pod_status !== "REVIEWED")
                    }
                    onClick={() => {
                      if (
                        window.confirm(
                          "Complete and close this trip? Operational details will become read-only.",
                        )
                      )
                        void mutate("complete", { closeout_reviewed: true });
                    }}
                  >
                    Complete trip
                  </button>
                  <p className="field-help">
                    {trip.pod_required && trip.pod_status !== "REVIEWED"
                      ? "Review POD in Delivery evidence before closeout. "
                      : ""}
                    Operational closeout does not mean an invoice has been paid.
                  </p>
                </div>
              )}
          </Card>
          {!own &&
            !closed &&
            ["SCHEDULED", "DISPATCHED"].includes(trip.current_milestone) &&
            can(identity, "trips.assign") &&
            can(identity, "dispatch.manage") && (
              <AssignmentEditor
                trip={trip}
                busy={busy}
                onAssign={(vehicle_id, driver_id) =>
                  mutate("assign", { vehicle_id, driver_id })
                }
              />
            )}
          {!own && !closed && can(identity, "trips.update") && (
            <Card className="master-card" title="Operator notes">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void mutate(
                    "notes",
                    { dispatcher_notes: notes || null },
                    "PATCH",
                  );
                }}
              >
                <label>
                  Replace operator notes
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    maxLength={4000}
                    rows={3}
                  />
                </label>
                <button className="button secondary" disabled={busy}>
                  Save notes
                </button>
              </form>
            </Card>
          )}
          {!own &&
            !closed &&
            trip.current_status !== "DELIVERED" &&
            can(identity, "trips.cancel") && (
              <Card className="master-card" title="Cancel trip">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (
                      window.confirm(
                        "Cancel this trip permanently? Its history will be retained.",
                      )
                    )
                      void mutate("cancel", { reason });
                  }}
                >
                  <label>
                    Cancellation reason
                    <textarea
                      required
                      minLength={3}
                      maxLength={2000}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      rows={3}
                    />
                  </label>
                  <button className="button secondary" disabled={busy}>
                    Cancel trip
                  </button>
                </form>
              </Card>
            )}
        </div>
      </div>
      </section>
      <section
        id={own ? undefined : "trip-tracking"}
        className={own ? undefined : "trip-section"}
      >
        <Card title="Milestone timeline" className="master-card audit-history">
        {timelineError ? (
          <ErrorState message={timelineError} />
        ) : !timeline ? (
          <LoadingState />
        ) : (
          <ol className="trip-timeline">
            {timeline.map((item) => (
              <li key={item.id}>
                <span className="timeline-dot" />
                <div>
                  <strong>{human(item.milestone_type)}</strong>
                  <time dateTime={item.occurred_at}>
                    {dateLabel(item.occurred_at)}
                  </time>
                  <small>
                    {human(item.source)}
                    {!own ? ` · Recorded ${dateLabel(item.recorded_at)}` : ""}
                  </small>
                  {!own && item.notes && <p>{item.notes}</p>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </Card>
      </section>
      {can(identity, own ? "driver_expense.read_own" : "expenses.read") && (
        <section
          id={own ? undefined : "trip-expenses"}
          className={own ? undefined : "trip-section"}
        >
          <ExpensesPanel
            trip={trip}
            identity={identity}
            own={own}
            onChanged={() => setRevision((v) => v + 1)}
          />
        </section>
      )}
      {!own && can(identity, "pod.read") && (
        <section id="trip-pod" className="trip-section">
          <DeliveryPanel
            trip={trip}
            identity={identity}
            own={false}
            onChanged={() => {
              setMessage("Delivery record saved successfully.");
              setRevision((value) => value + 1);
            }}
          />
        </section>
      )}
      {!own &&
        can(identity, "trip_profitability.read") &&
        can(identity, "trip_financials.read") &&
        can(identity, "expenses.read") && (
          <section id="trip-financial" className="trip-section">
            <FinancialPanel trip={trip} identity={identity} revision={revision} />
          </section>
        )}
      {!own &&
        (!isClientDemo(identity) || can(identity, "audit.read")) && (
          <section id="trip-activity" className="trip-section trip-activity-stack">
            {!isClientDemo(identity) && (
              <TripAssignmentHistory id={id} revision={revision} />
            )}
            {can(identity, "audit.read") && (
              <TripAudit id={id} revision={revision} />
            )}
          </section>
        )}
    </div>
  );
}
function AssignmentEditor({
  trip,
  busy,
  onAssign,
}: {
  trip: TripRecord;
  busy: boolean;
  onAssign: (vehicle: string, driver: string) => Promise<void>;
}) {
  const [vehicle, setVehicle] = useState(trip.vehicle_id ?? ""),
    [driver, setDriver] = useState(trip.driver_id ?? "");
  return (
    <Card className="master-card" title="Trip assignment">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void onAssign(vehicle, driver);
        }}
      >
        <ResourcePicker
          domain="vehicles"
          label="Trip vehicle"
          value={vehicle}
          onChange={setVehicle}
          required
          eligibleOnly
        />
        <ResourcePicker
          domain="drivers"
          label="Trip driver"
          value={driver}
          onChange={setDriver}
          required
          eligibleOnly
        />
        <button
          className="button primary"
          disabled={busy || !vehicle || !driver}
        >
          {trip.vehicle_id ? "Reassign trip" : "Assign trip"}
        </button>
        <p className="field-help">
          This does not change the vehicle’s fleet-master driver assignment.
        </p>
      </form>
    </Card>
  );
}
function TripAssignmentHistory({
  id,
  revision,
}: {
  id: string;
  revision: number;
}) {
  const { data, error } = useLoad<
    {
      id: string;
      vehicle_id: string;
      driver_id: string;
      assigned_at: string;
      ended_at: string | null;
      is_current: boolean;
    }[]
  >(`/trips/${id}/assignments`, revision);
  return (
    <Card className="master-card audit-history" title="Trip assignment history">
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState />
      ) : !data.length ? (
        <p className="small muted">No assignment yet.</p>
      ) : (
        <ul>
          {data.map((item) => (
            <li key={item.id}>
              <Link
                className="record-link"
                href={`/fleet/vehicles/${item.vehicle_id}`}
              >
                Vehicle record
              </Link>
              <Link
                className="record-link"
                href={`/fleet/drivers/${item.driver_id}`}
              >
                Driver record
              </Link>
              <span>
                {dateLabel(item.assigned_at)} →{" "}
                {item.ended_at ? dateLabel(item.ended_at) : "Current"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
function TripAudit({ id, revision }: { id: string; revision: number }) {
  const [offset, setOffset] = useState(0);
  const { data, error } = useLoad<
    { id: string; action: string; created_at: string; actor_user_id: string }[]
  >(
    `/audit-logs?entity_type=trip&entity_id=${id}&limit=20&offset=${offset}`,
    revision,
  );
  return (
    <Card className="master-card audit-history" title="Audit history">
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState />
      ) : (
        <ul>
          {data.map((item) => (
            <li key={item.id}>
              <strong>{human(item.action.replace("trip.", "Trip "))}</strong>
              <span>{dateLabel(item.created_at)}</span>
              <small>Actor: {item.actor_user_id}</small>
            </li>
          ))}
        </ul>
      )}
      <div className="master-actions">
        <button
          className="button secondary"
          disabled={!offset}
          onClick={() => setOffset(offset - 20)}
        >
          Previous events
        </button>
        <button
          className="button secondary"
          disabled={!data || data.length < 20}
          onClick={() => setOffset(offset + 20)}
        >
          More events
        </button>
      </div>
    </Card>
  );
}

export function DriverTrips({ compact = false }: { compact?: boolean }) {
  const [history, setHistory] = useState(false),
    [offset, setOffset] = useState(0),
    [revision, setRevision] = useState(0);
  const { data, error } = useLoad<Page<TripRecord>>(
    `/driver/trips?history=${history}&limit=20&offset=${offset}`,
    revision,
  );
  return (
    <div className={compact ? "" : "driver-content"}>
      {!compact && (
        <PageHeader
          title="Your trips"
          description="Your assigned work, one clear next step."
        />
      )}
      {!compact && (
        <div className="trip-views">
          <button
            aria-pressed={!history}
            onClick={() => {
              setHistory(false);
              setOffset(0);
            }}
          >
            Assigned trips
          </button>
          <button
            aria-pressed={history}
            onClick={() => {
              setHistory(true);
              setOffset(0);
            }}
          >
            Trip history
          </button>
        </div>
      )}
      {error ? (
        <>
          <ErrorState message={error} />
          <button
            className="button secondary"
            onClick={() => setRevision(revision + 1)}
          >
            Retry
          </button>
        </>
      ) : !data ? (
        <LoadingState />
      ) : !data.total ? (
        <Card className="current-trip">
          <EmptyState
            title={history ? "No trip history yet" : "No assigned trips"}
            description={
              history
                ? "Closed trips will appear here."
                : "Your dispatcher will assign your next delivery."
            }
            icon={<Truck />}
          />
          {!history && <DriverPrimaryAction />}
        </Card>
      ) : (
        <div className="driver-trip-list">
          {data.items.map((trip) => (
            <Card className="current-trip" key={trip.id}>
              <div className="trip-card-title">
                <strong>{trip.trip_number}</strong>
                <TripBadge value={trip.current_status} />
              </div>
              <h2>
                {trip.pickup_name} → {trip.delivery_name}
              </h2>
              <p className="small muted">
                {dateLabel(trip.scheduled_pickup_at)}
              </p>
              <div className="route-placeholder">
                <div>
                  <span className="stop-dot" />
                  <span>
                    {trip.pickup_name}
                    <small>{trip.pickup_address}</small>
                  </span>
                </div>
                <div>
                  <MapPin size={16} />
                  <span>
                    {trip.delivery_name}
                    <small>{trip.delivery_address}</small>
                  </span>
                </div>
              </div>
              <p className="small">
                Vehicle: {trip.vehicle_unit ?? "Awaiting assignment"}
              </p>
              <Link
                className="button primary driver-cta"
                href={`/driver/trips/${trip.id}`}
              >
                {trip.next_action_label ?? "View trip"}
                <ArrowRight size={18} />
              </Link>
            </Card>
          ))}
        </div>
      )}
      {data && data.total > 0 && (
        <Pagination data={data} offset={offset} onChange={setOffset} />
      )}
    </div>
  );
}
