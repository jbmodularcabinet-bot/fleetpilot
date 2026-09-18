"use client";
import { useEffect, useState } from "react";
import { Building2, Check, ShieldCheck, Users } from "lucide-react";
import { can } from "@fleetpilot/auth";
import type {
  Identity,
  Membership,
  Organization,
  Role,
} from "@fleetpilot/types";
import { Card, ErrorState, LoadingState, StatusBadge } from "@fleetpilot/ui";
import { request } from "@/lib/client";
import { useHydrated } from "@/lib/hydrated";

export function OrganizationForm({ identity }: { identity: Identity }) {
  const ready = useHydrated();
  const [org, setOrg] = useState(identity.organization);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const editable = can(identity, "organization.manage");
  return (
    <div className="settings-grid">
      <Card title="Organization details">
        <div className="organization-banner">
          <span className="icon-box">
            <Building2 />
          </span>
          <div>
            <strong>{org.name}</strong>
            <p className="small muted">Your business, your workspace.</p>
          </div>
          <StatusBadge tone="positive">Active</StatusBadge>
        </div>
        <form
          method="post"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            setSaved(false);
            const { name, legal_name, timezone, currency, country } = org;
            try {
              setOrg(
                await request<Organization>(
                  `/organizations/${org.id}`,
                  "PATCH",
                  { name, legal_name, timezone, currency, country },
                ),
              );
              setSaved(true);
            } catch (err) {
              setError(err instanceof Error ? err.message : "Unable to save");
            } finally {
              setBusy(false);
            }
          }}
        >
          <fieldset disabled={!editable || busy || !ready}>
            <div className="form-grid">
              {(
                [
                  ["name", "Organization name"],
                  ["legal_name", "Legal name (optional)"],
                  ["timezone", "Timezone"],
                  ["currency", "Currency (ISO code)"],
                  ["country", "Country (ISO code)"],
                ] as const
              ).map(([key, label]) => (
                <label key={key}>
                  {label}
                  <input
                    name={key}
                    value={org[key] ?? ""}
                    required={key !== "legal_name"}
                    maxLength={
                      key === "currency"
                        ? 3
                        : key === "country"
                          ? 2
                          : key === "name"
                            ? 120
                            : 200
                    }
                    onChange={(e) => {
                      setOrg({ ...org, [key]: e.target.value });
                      setSaved(false);
                    }}
                  />
                </label>
              ))}
              <label>
                Workspace address
                <input value={org.slug} disabled />
                <span className="field-help">
                  Set when your organization is provisioned.
                </span>
              </label>
            </div>
            {editable && (
              <div className="form-actions">
                <span className="small muted">
                  Changes are recorded in your audit log.
                </span>
                <button className="button primary" type="submit">
                  {busy ? "Saving…" : "Save changes"}
                </button>
              </div>
            )}
          </fieldset>
          {!editable && (
            <p className="small muted">
              Your role has read-only access to these settings.
            </p>
          )}
          {error && <ErrorState message={error} />}
          {saved && (
            <p role="status" className="success-message">
              <Check size={16} />
              Organization details saved.
            </p>
          )}
        </form>
      </Card>
      <Card className="settings-aside">
        <ShieldCheck size={26} />
        <h2>Your organization stays yours.</h2>
        <p>
          Only authorized members can access this workspace. Settings and access
          changes are recorded for accountability.
        </p>
        <div className="aside-detail">
          <span>YOUR ROLE</span>
          <strong>{identity.membership.role}</strong>
        </div>
        <div className="aside-detail">
          <span>WORKSPACE TIMEZONE</span>
          <strong>{org.timezone}</strong>
        </div>
      </Card>
    </div>
  );
}

const roles: Role[] = [
  "OWNER",
  "MANAGER",
  "DISPATCHER",
  "DRIVER",
  "ACCOUNTING",
  "MAINTENANCE",
  "ADMIN",
];
function MemberRow({
  member,
  identity,
  onSaved,
}: {
  member: Membership;
  identity: Identity;
  onSaved: () => void;
}) {
  const [role, setRole] = useState(member.role);
  const [active, setActive] = useState(member.active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const canManage =
    can(identity, "users.manage") && member.user_id !== identity.user.id;
  return (
    <tr>
      <td>
        <strong>{member.name}</strong>
        <small>{member.email}</small>
      </td>
      <td>
        <select
          aria-label={`Role for ${member.name}`}
          disabled={!canManage || busy}
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
        >
          {roles.map((value) => (
            <option value={value} key={value}>
              {value}
            </option>
          ))}
        </select>
      </td>
      <td>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={active}
            disabled={!canManage || busy}
            onChange={(e) => setActive(e.target.checked)}
          />
          Active
        </label>
      </td>
      <td>
        <button
          className="button secondary"
          disabled={
            !canManage ||
            busy ||
            (role === member.role && active === member.active)
          }
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await request(`/memberships/${member.id}`, "PATCH", {
                role,
                active,
              });
              onSaved();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Unable to save");
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Saving…" : "Save"}
        </button>
        {error && (
          <p role="alert" className="field-error">
            {error}
          </p>
        )}
      </td>
    </tr>
  );
}
export function MembershipSettings({ identity }: { identity: Identity }) {
  const [members, setMembers] = useState<Membership[] | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("DRIVER");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(0);
  async function load() {
    try {
      setMembers(
        await request<Membership[]>(
          `/memberships?limit=50&offset=${page * 50}`,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load members");
    }
  }
  useEffect(() => {
    let cancelled = false;
    request<Membership[]>(`/memberships?limit=50&offset=${page * 50}`)
      .then((value) => {
        if (!cancelled) setMembers(value);
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Could not load members",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [page]);
  return (
    <>
      <Card title="People & access" action={<Users size={20} />}>
        <p className="muted">
          Manage who can access {identity.organization.name}.
        </p>
        {error && <ErrorState message={error} />}
        {saved && (
          <p role="status" className="success-message">
            {saved}
          </p>
        )}
        {!members ? (
          <LoadingState />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Team member</th>
                    <th>Role</th>
                    <th>Membership</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((member) => (
                    <MemberRow
                      key={`${member.id}-${member.role}-${member.active}`}
                      member={member}
                      identity={identity}
                      onSaved={() => {
                        setSaved(
                          "Membership updated and recorded in the audit log.",
                        );
                        void load();
                      }}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <div className="form-actions">
              <button
                className="button secondary"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </button>
              <span className="small">Page {page + 1}</span>
              <button
                className="button secondary"
                disabled={members.length < 50}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </div>
          </>
        )}
      </Card>
      {can(identity, "users.manage") && (
        <Card title="Add an existing account" className="add-member">
          <p className="muted">
            Accounts must first be provisioned by a system administrator. Email
            invitations are not enabled in this batch.
          </p>
          <form
            method="post"
            className="inline-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              setSaved("");
              try {
                await request("/memberships", "POST", { email, role });
                setEmail("");
                setSaved("Membership added.");
                await load();
              } catch (err) {
                setError(
                  err instanceof Error ? err.message : "Unable to add member",
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Email address
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <label>
              Role
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
              >
                {roles.map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <button className="button primary" disabled={busy}>
              {busy ? "Adding…" : "Add member"}
            </button>
          </form>
        </Card>
      )}
    </>
  );
}
