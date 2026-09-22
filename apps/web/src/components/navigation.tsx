"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { canReport, FILTER_KEYS } from "@/lib/reporting";
import { useState } from "react";
import {
  ArrowUpRight,
  ChartSpline,
  Bell,
  ChevronDown,
  CircleUserRound,
  WalletCards,
  Gauge,
  House,
  LogOut,
  Menu,
  ReceiptText,
  Settings,
  ShieldCheck,
  BrainCircuit,
  Truck,
  Building2,
  Route,
  X,
} from "lucide-react";
import { FleetPilotLogo, StatusBadge } from "@fleetpilot/ui";
import { can, homeFor, isClientDemo } from "@fleetpilot/auth";
import type { Identity } from "@fleetpilot/types";
import { beforeAccountExit, clearOffline } from "@/lib/offline";
import { request } from "@/lib/client";

export function Logout() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <div>
      <button
        className="text-button logout"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            if (!(await beforeAccountExit())) {
              setBusy(false);
              return;
            }
            await request("/auth/logout", "POST");
            await clearOffline();
            window.location.assign("/login");
          } catch {
            setError("Sign out failed. Retry.");
            setBusy(false);
          }
        }}
      >
        <LogOut size={16} />
        {busy ? "Signing out…" : "Sign out"}
      </button>
      {error && <span role="alert">{error}</span>}
    </div>
  );
}
export function Sidebar({ identity }: { identity: Identity }) {
  const path = usePathname();
  const search = useSearchParams();
  const reportScope = new URLSearchParams();
  FILTER_KEYS.forEach((key) => {
    const value = search.get(key);
    if (value) reportScope.set(key, value);
  });
  const reportingSuffix = reportScope.size ? `?${reportScope.toString()}` : "";
  const [open, setOpen] = useState(false);
  const future = [
    [Route, "Operations"],
    [Truck, "Fleet"],
    [WalletCards, "Money"],
    [Building2, "Customers"],
    [BrainCircuit, "Intelligence"],
    [ChartSpline, "Reports"],
  ] as const;
  return (
    <>
      <button
        className="mobile-menu icon-button"
        aria-label="Open navigation"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? <X /> : <Menu />}
      </button>
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <Link href={homeFor(identity)} aria-label="FleetPilot home">
          <FleetPilotLogo />
        </Link>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav aria-label="Main navigation">
          {can(identity, "owner_dashboard.view") && (
            <Link
              className={`nav-item ${path === "/dashboard" ? "selected" : ""}`}
              href={"/dashboard" + reportingSuffix}
              onClick={() => setOpen(false)}
            >
              <Gauge size={19} />
              Overview
            </Link>
          )}
          {future.map(([Icon, label]) =>
            label === "Operations" && can(identity, "dispatch.read") ? (
              <div key={label}>
                <span className="nav-item">
                  <Route size={19} />
                  Operations
                </span>
                <Link
                  className={`nav-item nav-child ${path.startsWith("/dispatch") || path.startsWith("/trips") ? "selected" : ""}`}
                  href="/dispatch"
                  onClick={() => setOpen(false)}
                >
                  Dispatch Board
                </Link>
              </div>
            ) : label === "Customers" && can(identity, "customers.read") ? (
              <Link
                key={label}
                className={`nav-item ${path.startsWith("/customers") ? "selected" : ""}`}
                href="/customers"
                onClick={() => setOpen(false)}
              >
                <Icon size={19} />
                Customers
              </Link>
            ) : label === "Fleet" &&
              (can(identity, "vehicles.read") ||
                can(identity, "drivers.read")) ? (
              <div key={label}>
                <span className="nav-item">
                  <Truck size={19} />
                  Fleet
                </span>
                {can(identity, "vehicles.read") && (
                  <Link
                    className={`nav-item nav-child ${path.startsWith("/fleet/vehicles") ? "selected" : ""}`}
                    href="/fleet/vehicles"
                    onClick={() => setOpen(false)}
                  >
                    Vehicles
                  </Link>
                )}
                {can(identity, "drivers.read") && (
                  <Link
                    className={`nav-item nav-child ${path.startsWith("/fleet/drivers") ? "selected" : ""}`}
                    href="/fleet/drivers"
                    onClick={() => setOpen(false)}
                  >
                    Drivers
                  </Link>
                )}
              </div>
            ) : label === "Intelligence" || label === "Reports" ? (
              canReport(identity) ? (
                <Link
                  key={label}
                  className={`nav-item ${path.startsWith(label === "Intelligence" ? "/intelligence" : "/reports") ? "selected" : ""}`}
                  href={
                    (label === "Intelligence" ? "/intelligence" : "/reports") +
                    reportingSuffix
                  }
                  onClick={() => setOpen(false)}
                >
                  <Icon size={19} />
                  {label}
                </Link>
              ) : null
            ) : (
              <button
                className="nav-item"
                disabled
                key={label}
                title="Available in a later batch"
              >
                <Icon size={19} />
                {label}
                <span className="nav-later">Soon</span>
              </button>
            ),
          )}
          {!isClientDemo(identity) && (
            <Link
              className={`nav-item ${path.startsWith("/settings") ? "selected" : ""}`}
              href="/settings/organization"
              onClick={() => setOpen(false)}
            >
              <Settings size={19} />
              Settings
            </Link>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <ShieldCheck size={22} />
            <strong>
              Your fleet’s future.
              <br />
              You stay in control.
            </strong>
            <span>Run the fleet. Not the chaos.</span>
            <div className="road-lines" aria-hidden="true" />
          </div>
          <div className="foundation-note">
            FLEETPILOT <span>DISPATCH · 04</span>
          </div>
        </div>
      </aside>
    </>
  );
}
export function TopNav({ identity }: { identity: Identity }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <header className="top-nav">
      <div className="workspace-select">
        <span className="workspace-monogram">
          {identity.organization.name[0]}
        </span>
        <label className="sr-only" htmlFor="organization-switch">
          Active organization
        </label>
        <select
          id="organization-switch"
          aria-label="Active organization"
          value={identity.organization.id}
          disabled={busy || identity.organizations.length < 2}
          onChange={async (e) => {
            setBusy(true);
            try {
              await request("/organization-selection", "POST", {
                organization_id: e.target.value,
              });
              window.location.assign("/");
            } catch (err) {
              setError(
                err instanceof Error
                  ? err.message
                  : "Could not switch organization",
              );
              setBusy(false);
            }
          }}
        >
          {identity.organizations.map((org) => (
            <option value={org.id} key={org.id}>
              {org.name}
            </option>
          ))}
        </select>
        <ChevronDown size={14} />
        {identity.organization.slug === "demo-logistics" && (
          <StatusBadge>Demo workspace</StatusBadge>
        )}
      </div>
      <div className="account">
        <span className="secure-label">
          <ShieldCheck size={14} /> Secure workspace
        </span>
        <span className="avatar">
          {identity.user.name
            .split(" ")
            .map((v) => v[0])
            .slice(0, 2)
            .join("")}
        </span>
        <span>
          <strong>{identity.user.name}</strong>
          <small>{identity.membership.role.toLowerCase()}</small>
        </span>
        <Logout />
      </div>
      {error && <span role="alert">{error}</span>}
    </header>
  );
}
export function MobileBottomNav() {
  const path = usePathname();
  return (
    <nav className="bottom-nav" aria-label="Driver navigation">
      {[
        [House, "Home", "/driver"],
        [Truck, "Trips", "/driver/trips"],
        [ReceiptText, "Expenses", null],
        [Bell, "Alerts", null],
        [CircleUserRound, "Profile", "/driver/profile"],
      ].map(([Icon, label, href]) => {
        const Glyph = Icon as typeof House;
        return typeof href === "string" ? (
          <Link
            key={String(label)}
            href={href}
            className={path === href ? "active" : ""}
          >
            <Glyph size={21} />
            <span>{String(label)}</span>
          </Link>
        ) : (
          <button
            key={String(label)}
            disabled
            title="Available in a later batch"
          >
            <Glyph size={21} />
            <span>{String(label)}</span>
          </button>
        );
      })}
    </nav>
  );
}
export function SettingsNav({ identity }: { identity: Identity }) {
  const path = usePathname();
  return (
    <nav className="settings-nav" aria-label="Settings navigation">
      <Link
        aria-current={path === "/settings/organization" ? "page" : undefined}
        href="/settings/organization"
      >
        Organization
      </Link>
      {can(identity, "users.read") && (
        <Link
          aria-current={path === "/settings/users" ? "page" : undefined}
          href="/settings/users"
        >
          People & access
        </Link>
      )}
      <span>
        Organization settings <ArrowUpRight size={14} />
      </span>
    </nav>
  );
}
