"use client";
import { VehicleMaintenance } from "./maintenance";
import { FuelHistory } from "./expenses";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Plus, Search, Truck, Users } from "lucide-react";
import {
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
} from "@fleetpilot/ui";
import type { Identity, Membership } from "@fleetpilot/types";
import { can } from "@fleetpilot/auth";
import { request } from "@/lib/client";
import { useHydrated } from "@/lib/hydrated";
import {
  config,
  formPayload,
  labelFor,
  recordName,
  type Assignment,
  type Domain,
  type MasterRecord,
  type Page,
} from "@/lib/master-data";

function useData<T>(path: string, revision = 0): { data?: T; error?: string } {
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
      .catch((error) => {
        if (alive)
          setResult({
            path,
            revision,
            error:
              error instanceof Error
                ? error.message
                : "Unable to load records.",
          });
      });
    return () => {
      alive = false;
    };
  }, [path, revision]);
  return result?.path === path && result.revision === revision ? result : {};
}
function Badge({ status }: { status: unknown }) {
  return (
    <StatusBadge
      tone={
        status === "ACTIVE" || status === "AVAILABLE"
          ? "positive"
          : status === "ASSIGNED"
            ? "active"
            : "neutral"
      }
    >
      {String(status).replaceAll("_", " ")}
    </StatusBadge>
  );
}
function Pager({
  total,
  offset,
  limit,
  onChange,
}: {
  total: number;
  offset: number;
  limit: number;
  onChange: (offset: number) => void;
}) {
  return (
    <div className="master-pager">
      <span className="small muted">
        {total
          ? `${offset + 1}–${Math.min(offset + limit, total)} of ${total}`
          : "0 records"}
      </span>
      <div>
        <button
          className="button secondary"
          disabled={!offset}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button
          className="button secondary"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
export function MasterList({
  domain,
  identity,
}: {
  domain: Domain;
  identity: Identity;
}) {
  const spec = config[domain];
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("created_at");
  const [direction, setDirection] = useState("desc");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const hydrated = useHydrated();
  const params = new URLSearchParams({
    search: query,
    sort,
    direction,
    limit: "20",
    offset: String(offset),
    ...(status ? { status } : {}),
  });
  const { data, error } = useData<Page<MasterRecord>>(
    `/${domain}?${params}`,
    revision,
  );
  return (
    <>
      <PageHeader title={spec.title} description={spec.description}>
        {can(identity, `${domain}.create`) && (
          <Link className="button primary" href={`${spec.path}/new`}>
            <Plus size={17} /> Add {spec.singular}
          </Link>
        )}
      </PageHeader>
      {domain !== "customers" && (
        <nav className="settings-nav" aria-label="Fleet navigation">
          <Link
            href="/fleet/vehicles"
            aria-current={domain === "vehicles" ? "page" : undefined}
          >
            Vehicles
          </Link>
          <Link
            href="/fleet/drivers"
            aria-current={domain === "drivers" ? "page" : undefined}
          >
            Drivers
          </Link>
        </nav>
      )}
      <Card className="master-card">
        <form
          className="master-toolbar"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(search);
            setOffset(0);
          }}
        >
          <label className="master-search">
            Search {spec.title.toLowerCase()}
            <div>
              <Search size={17} />
              <input
                value={search}
                maxLength={160}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={
                  domain === "vehicles"
                    ? "Unit, plate, make or model"
                    : domain === "customers"
                      ? "Company, contact or code"
                      : "Name, employee or license number"
                }
              />
            </div>
          </label>
          <button className="button secondary" disabled={!hydrated}>
            Search
          </button>
          <label>
            Status
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All statuses</option>
              {spec.statuses.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            Sort by
            <select
              value={sort}
              onChange={(e) => {
                setSort(e.target.value);
                setOffset(0);
              }}
            >
              {spec.sort.map((value) => (
                <option key={value} value={value}>
                  {labelFor(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Order
            <select
              value={direction}
              onChange={(e) => {
                setDirection(e.target.value);
                setOffset(0);
              }}
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>
        </form>
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
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={domain === "vehicles" ? <Truck /> : <Users />}
            title={
              query || status
                ? "No matching records"
                : `No ${spec.title.toLowerCase()} yet`
            }
            description={
              query || status
                ? "Try another search or status filter."
                : `Add your first ${spec.singular} to get started.`
            }
          />
        ) : (
          <div className="table-scroll">
            <table>
              <caption className="sr-only">
                {spec.title} in {identity.organization.name}
              </caption>
              <thead>
                <tr>
                  {spec.columns.map((key) => (
                    <th scope="col" key={key}>
                      {labelFor(key)}
                    </th>
                  ))}
                  <th scope="col">Details</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.id}>
                    {spec.columns.map((key, index) => (
                      <td key={key}>
                        {key === spec.statusKey ? (
                          <Badge status={row[key]} />
                        ) : index === 0 ? (
                          <Link
                            className="record-link"
                            href={`${spec.path}/${row.id}`}
                          >
                            {row[key] ?? "—"}
                          </Link>
                        ) : (
                          (row[key] ?? "—")
                        )}
                      </td>
                    ))}
                    <td>
                      <Link
                        className="record-link"
                        href={`${spec.path}/${row.id}`}
                        aria-label={`View ${recordName(domain, row)}`}
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
          <Pager
            total={data.total}
            offset={offset}
            limit={20}
            onChange={setOffset}
          />
        )}
      </Card>
    </>
  );
}

export function MasterEditor({
  domain,
  identity,
  id,
}: {
  domain: Domain;
  identity: Identity;
  id?: string;
}) {
  const { data, error } = useData<MasterRecord>(
    id ? `/${domain}/${id}` : "/me",
  );
  if (error) return <ErrorState message={error} />;
  if (!data) return <LoadingState />;
  return (
    <RecordForm
      key={id ?? "new"}
      domain={domain}
      identity={identity}
      initial={id ? data : undefined}
    />
  );
}
function RecordForm({
  domain,
  identity,
  initial,
}: {
  domain: Domain;
  identity: Identity;
  initial?: MasterRecord;
}) {
  const spec = config[domain],
    router = useRouter(),
    hydrated = useHydrated();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      spec.fields.map((field) => [
        field.key,
        String(
          initial?.[field.key] ??
            (field.key === "employment_status" ? "ACTIVE" : ""),
        ),
      ]),
    ),
  );
  const [userId, setUserId] = useState(String(initial?.user_id ?? ""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [members, setMembers] = useState<Membership[]>([]);
  const [membersError, setMembersError] = useState("");
  const allowLink = domain === "drivers" && can(identity, "users.manage");
  useEffect(() => {
    if (!allowLink) return;
    let alive = true;
    (async () => {
      const all: Membership[] = [];
      for (let offset = 0; ; offset += 100) {
        const page = await request<Membership[]>(
          `/memberships?limit=100&offset=${offset}`,
        );
        all.push(...page);
        if (page.length < 100) break;
      }
      if (alive)
        setMembers(
          all.filter((member) => member.active && member.role === "DRIVER"),
        );
    })().catch(() => {
      if (alive)
        setMembersError(
          "Account list unavailable. Retry this page to change account linkage.",
        );
    });
    return () => {
      alive = false;
    };
  }, [allowLink]);
  return (
    <>
      <Link
        className="master-back"
        href={initial ? `${spec.path}/${initial.id}` : spec.path}
      >
        <ArrowLeft size={16} /> Back to{" "}
        {initial ? "details" : spec.title.toLowerCase()}
      </Link>
      <PageHeader
        title={`${initial ? "Edit" : "Add"} ${spec.singular}`}
        description={
          domain === "drivers"
            ? "A driver profile does not need a login account."
            : "Keep your fleet information accurate and up to date."
        }
      />
      <Card className="master-card">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            if (
              domain === "vehicles" &&
              Boolean(values.capacity) !== Boolean(values.capacity_unit)
            ) {
              setError(
                "Enter both capacity and capacity unit, or leave both blank.",
              );
              return;
            }
            setBusy(true);
            try {
              const payload = {
                ...formPayload(domain, values),
                ...(domain === "drivers" ? { user_id: userId || null } : {}),
              };
              const saved = await request<MasterRecord>(
                `/${domain}${initial ? `/${initial.id}` : ""}`,
                initial ? "PATCH" : "POST",
                payload,
              );
              router.push(`${spec.path}/${saved.id}?saved=1`);
              router.refresh();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Unable to save.");
              setBusy(false);
            }
          }}
        >
          <p className="small muted master-help">
            Fields marked * are required.
          </p>
          <fieldset disabled={busy || !hydrated}>
            <div className="form-grid">
              {spec.fields.map((field) => (
                <label key={field.key}>
                  {field.label}
                  {field.required ? " *" : ""}
                  {field.options ? (
                    <select
                      value={values[field.key]}
                      required={field.required}
                      onChange={(e) =>
                        setValues({ ...values, [field.key]: e.target.value })
                      }
                    >
                      {!field.required && (
                        <option value="">Not specified</option>
                      )}
                      {field.options.map((value) => (
                        <option key={value}>{value}</option>
                      ))}
                    </select>
                  ) : field.type === "textarea" ? (
                    <textarea
                      value={values[field.key]}
                      maxLength={field.max}
                      rows={3}
                      onChange={(e) =>
                        setValues({ ...values, [field.key]: e.target.value })
                      }
                    />
                  ) : (
                    <input
                      type={field.type ?? "text"}
                      required={field.required}
                      value={values[field.key]}
                      minLength={
                        field.type !== "number" ? field.min : undefined
                      }
                      maxLength={
                        field.type !== "number" ? field.max : undefined
                      }
                      min={field.type === "number" ? field.min : undefined}
                      max={field.type === "number" ? field.max : undefined}
                      step={field.step}
                      pattern={field.pattern}
                      onChange={(e) =>
                        setValues({ ...values, [field.key]: e.target.value })
                      }
                    />
                  )}
                </label>
              ))}
              {allowLink && (
                <label>
                  Linked driver account
                  <select
                    value={userId}
                    disabled={Boolean(membersError)}
                    onChange={(e) => setUserId(e.target.value)}
                  >
                    <option value="">No login account</option>
                    {userId && !members.some((m) => m.user_id === userId) && (
                      <option value={userId}>Currently linked account</option>
                    )}
                    {members.map((member) => (
                      <option key={member.user_id} value={member.user_id}>
                        {member.name} · {member.email}
                      </option>
                    ))}
                  </select>
                  <span className="field-help">
                    Only existing active driver accounts in this organization
                    can be linked.
                  </span>
                </label>
              )}
            </div>
          </fieldset>
          {membersError && <ErrorState message={membersError} />}{" "}
          {error && <ErrorState message={error} />}
          <div className="form-actions">
            <Link
              className="button secondary"
              href={initial ? `${spec.path}/${initial.id}` : spec.path}
            >
              Cancel
            </Link>
            <button className="button primary" disabled={busy || !hydrated}>
              {busy ? "Saving…" : `Save ${spec.singular}`}
            </button>
          </div>
        </form>
      </Card>
    </>
  );
}

export function MasterDetail({
  domain,
  identity,
  id,
  saved = false,
}: {
  domain: Domain;
  identity: Identity;
  id: string;
  saved?: boolean;
}) {
  const spec = config[domain];
  const [revision, setRevision] = useState(0);
  const { data: row, error } = useData<MasterRecord>(
    `/${domain}/${id}`,
    revision,
  );
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [message, setMessage] = useState(
    saved ? "Record saved successfully." : "",
  );
  if (error)
    return (
      <>
        <ErrorState message={error} />
        <Link href={spec.path}>Back to {spec.title.toLowerCase()}</Link>
      </>
    );
  if (!row) return <LoadingState />;
  const inactive = row[spec.statusKey] === "INACTIVE";
  return (
    <>
      <Link className="master-back" href={spec.path}>
        <ArrowLeft size={16} /> All {spec.title.toLowerCase()}
      </Link>
      <PageHeader
        title={recordName(domain, row)}
        description={`${labelFor(spec.columns[0])}: ${row[spec.columns[0]]}`}
      >
        <div className="master-actions">
          <Badge status={row[spec.statusKey]} />
          {can(identity, `${domain}.update`) &&
            !(domain === "drivers" && inactive) && (
              <Link
                className="button secondary"
                href={`${spec.path}/${id}/edit`}
              >
                Edit {spec.singular}
              </Link>
            )}
          {can(identity, `${domain}.deactivate`) && (
            <button
              className="button secondary"
              disabled={busy}
              onClick={async () => {
                if (
                  !window.confirm(
                    `${inactive ? "Reactivate" : "Deactivate"} this ${spec.singular}? ${inactive ? "It will become available for use again." : "Its records and assignment history will be retained."}`,
                  )
                )
                  return;
                setBusy(true);
                setActionError("");
                try {
                  await request(
                    `/${domain}/${id}/${inactive ? "reactivate" : "deactivate"}`,
                    "POST",
                  );
                  setMessage(
                    `Record ${inactive ? "reactivated" : "deactivated"}.`,
                  );
                  setRevision(revision + 1);
                } catch (err) {
                  setActionError(
                    err instanceof Error
                      ? err.message
                      : "Unable to update status.",
                  );
                } finally {
                  setBusy(false);
                }
              }}
            >
              {inactive ? "Reactivate" : "Deactivate"}
            </button>
          )}
        </div>
      </PageHeader>
      {message && (
        <p className="success-message" role="status">
          {message}
        </p>
      )}
      {actionError && <ErrorState message={actionError} />}
      <div className="master-detail-grid">
        <Card
          title={`${labelFor(spec.singular)} information`}
          className="master-card"
        >
          <dl className="master-fields">
            {spec.fields.map((field) => (
              <div key={field.key}>
                <dt>{field.label}</dt>
                <dd>
                  {row[field.key] === null || row[field.key] === ""
                    ? "Not specified"
                    : String(row[field.key])}
                </dd>
              </div>
            ))}
            {domain === "drivers" && (
              <div>
                <dt>Login account</dt>
                <dd>{row.user_id ? "Linked" : "No login account linked"}</dd>
              </div>
            )}
            <div>
              <dt>Last updated</dt>
              <dd>{new Date(String(row.updated_at)).toLocaleString()}</dd>
            </div>
          </dl>
        </Card>
        {domain !== "customers" && can(identity, "assignments.read") && (
          <Assignments
            domain={domain}
            identity={identity}
            id={id}
            revision={revision}
            onChange={() => setRevision(revision + 1)}
          />
        )}
      </div>
      {domain === "vehicles" && can(identity, "maintenance.read") && (
        <VehicleMaintenance vehicle={id} identity={identity} />
      )}
      {domain === "vehicles" && can(identity, "fuel.read") && (
        <FuelHistory vehicle={id} />
      )}
      {can(identity, "audit.read") && (
        <AuditHistory domain={domain} id={id} revision={revision} />
      )}
    </>
  );
}

function Assignments({
  domain,
  identity,
  id,
  revision,
  onChange,
}: {
  domain: "vehicles" | "drivers";
  identity: Identity;
  id: string;
  revision: number;
  onChange: () => void;
}) {
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const filter = domain === "vehicles" ? "vehicle_id" : "driver_id";
  const other = domain === "vehicles" ? "drivers" : "vehicles";
  const { data: history, error: historyError } = useData<Page<Assignment>>(
    `/vehicle-driver-assignments?${filter}=${id}&limit=10&offset=${offset}`,
    revision,
  );
  const { data: current, error: currentError } = useData<Page<Assignment>>(
    `/vehicle-driver-assignments?${filter}=${id}&is_current=true`,
    revision,
  );
  const manage =
    can(identity, "assignments.manage") &&
    can(identity, "vehicles.assign_driver");
  const { data: candidates, error: candidateError } = useData<
    Page<MasterRecord>
  >(
    manage
      ? `/${other}?status=${other === "drivers" ? "ACTIVE" : "AVAILABLE"}&search=${encodeURIComponent(query)}&limit=100`
      : "/me",
    revision,
  );
  const active = current?.items[0];
  return (
    <Card
      className="master-card"
      title={domain === "vehicles" ? "Driver assignment" : "Vehicle assignment"}
    >
      {currentError ? (
        <ErrorState message={currentError} />
      ) : !current ? (
        <LoadingState />
      ) : active ? (
        <div className="assignment-current">
          <StatusBadge tone="active">Current assignment</StatusBadge>
          <Link
            className="record-link"
            href={
              domain === "vehicles"
                ? `/fleet/drivers/${active.driver_id}`
                : `/fleet/vehicles/${active.vehicle_id}`
            }
          >
            {domain === "vehicles" ? active.driver_name : active.unit_number}
          </Link>
          <span className="small muted">
            Since {new Date(active.assigned_at).toLocaleString()}
          </span>
          {manage && (
            <button
              className="button secondary"
              disabled={busy}
              onClick={async () => {
                if (
                  !window.confirm(
                    "Unassign this driver and vehicle? The assignment will remain in history.",
                  )
                )
                  return;
                setBusy(true);
                setError("");
                try {
                  await request(
                    `/vehicle-driver-assignments/${active.id}/unassign`,
                    "POST",
                  );
                  onChange();
                } catch (err) {
                  setError(
                    err instanceof Error ? err.message : "Unassignment failed.",
                  );
                } finally {
                  setBusy(false);
                }
              }}
            >
              Unassign
            </button>
          )}
        </div>
      ) : (
        <>
          <p className="small muted">No current assignment.</p>
          {manage && (
            <div className="assignment-form">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  setQuery(search);
                  setSelected("");
                }}
              >
                <label>
                  Find available {other}
                  <input
                    value={search}
                    maxLength={160}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </label>
                <button className="button secondary">Find</button>
              </form>
              {candidateError && <ErrorState message={candidateError} />}
              <label>
                {domain === "vehicles" ? "Choose driver" : "Choose vehicle"}
                <select
                  value={selected}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  <option value="">Select a record</option>
                  {candidates?.items
                    ?.filter(
                      (row) =>
                        other !== "drivers" ||
                        row.operational_status === "UNASSIGNED",
                    )
                    .map((row) => (
                      <option key={row.id} value={row.id}>
                        {recordName(other, row)} ·{" "}
                        {row[config[other].columns[0]]}
                      </option>
                    ))}
                </select>
              </label>
              {candidates && candidates.total > 100 && (
                <p className="small muted">
                  Showing up to 100 matches. Refine your search.
                </p>
              )}
              <label>
                Assignment notes
                <input
                  maxLength={4000}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </label>
              <button
                className="button primary"
                disabled={!selected || busy}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    await request("/vehicle-driver-assignments", "POST", {
                      vehicle_id: domain === "vehicles" ? id : selected,
                      driver_id: domain === "drivers" ? id : selected,
                      notes: notes || null,
                    });
                    setSelected("");
                    setNotes("");
                    onChange();
                  } catch (err) {
                    setError(
                      err instanceof Error ? err.message : "Assignment failed.",
                    );
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Assign {domain === "vehicles" ? "driver" : "vehicle"}
              </button>
            </div>
          )}
        </>
      )}
      {error && <ErrorState message={error} />}
      <h3 className="history-title">Assignment history</h3>
      {historyError ? (
        <ErrorState message={historyError} />
      ) : !history ? (
        <LoadingState />
      ) : !history.total ? (
        <p className="small muted">No assignment history yet.</p>
      ) : (
        <>
          <ol className="assignment-history">
            {history.items.map((item) => (
              <li key={item.id}>
                <strong>
                  {item.driver_name} · {item.unit_number}
                </strong>
                <Badge status={item.is_current ? "ASSIGNED" : "ENDED"} />
                <span>
                  {new Date(item.assigned_at).toLocaleString()} →{" "}
                  {item.unassigned_at
                    ? new Date(item.unassigned_at).toLocaleString()
                    : "Current"}
                </span>
                {item.notes && <p>{item.notes}</p>}
              </li>
            ))}
          </ol>
          <Pager
            total={history.total}
            offset={offset}
            limit={10}
            onChange={setOffset}
          />
        </>
      )}
    </Card>
  );
}
interface AuditEntry {
  id: string;
  action: string;
  created_at: string;
  actor_user_id: string;
}
function AuditHistory({
  domain,
  id,
  revision,
}: {
  domain: Domain;
  id: string;
  revision: number;
}) {
  const [offset, setOffset] = useState(0);
  const { data, error } = useData<AuditEntry[]>(
    `/audit-logs?entity_type=${config[domain].singular}&entity_id=${id}&limit=10&offset=${offset}`,
    revision,
  );
  return (
    <Card className="master-card audit-history" title="Audit history">
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState />
      ) : !data.length ? (
        <p className="small muted">No more audit records.</p>
      ) : (
        <ul>
          {data.map((row) => (
            <li key={row.id}>
              <strong>{row.action}</strong>
              <span>{new Date(row.created_at).toLocaleString()}</span>
              <small>Actor: {row.actor_user_id}</small>
            </li>
          ))}
        </ul>
      )}
      <div className="master-actions">
        <button
          className="button secondary"
          disabled={!offset}
          onClick={() => setOffset(offset - 10)}
        >
          Previous events
        </button>
        <button
          className="button secondary"
          disabled={!data || data.length < 10}
          onClick={() => setOffset(offset + 10)}
        >
          More events
        </button>
      </div>
    </Card>
  );
}

export function OwnDriverProfile() {
  const { data, error } = useData<{
    profile: Record<string, string | null> | null;
    assignment: Record<string, string> | null;
  }>("/driver-profile");
  return (
    <Card title="Driver profile & assignment">
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState />
      ) : !data.profile ? (
        <p className="small muted">
          Your driver profile is not linked yet. Contact your fleet
          administrator.
        </p>
      ) : (
        <>
          <dl>
            {Object.entries(data.profile).map(([key, value]) => (
              <div key={key}>
                <dt>{labelFor(key)}</dt>
                <dd>{value ?? "Not specified"}</dd>
              </div>
            ))}
          </dl>
          <h3 className="history-title">Current vehicle</h3>
          {data.assignment ? (
            <dl>
              {Object.entries(data.assignment).map(([key, value]) => (
                <div key={key}>
                  <dt>{labelFor(key)}</dt>
                  <dd>
                    {key === "assigned_at"
                      ? new Date(value).toLocaleString()
                      : value}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="small muted">No vehicle assigned.</p>
          )}
        </>
      )}
    </Card>
  );
}
