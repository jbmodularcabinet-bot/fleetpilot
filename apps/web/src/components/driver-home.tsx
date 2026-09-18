"use client";
import { DriverDefect } from "./maintenance";
import { can } from "@fleetpilot/auth";
import Link from "next/link";
import {
  Bell,
  Navigation,
  Phone,
  TriangleAlert,
  ShieldCheck,
} from "lucide-react";
import { FleetPilotLogo } from "@fleetpilot/ui";
import type { Identity } from "@fleetpilot/types";
import { DriverTrips } from "@/components/trips";
export function DriverHomeContent({ identity }: { identity: Identity }) {
  return (
    <>
      <div className="driver-brand">
        <FleetPilotLogo compact />
        <span>DRIVER APP</span>
      </div>
      <div className="driver-content">
        <header className="driver-header">
          <Link
            className="avatar"
            href="/driver/profile"
            aria-label="Open profile"
          >
            {identity.user.name[0]}
          </Link>
          <div>
            <p>Welcome back,</p>
            <h1>{identity.user.name.split(" ")[0]}.</h1>
          </div>
          <button
            className="icon-button"
            aria-label="Alerts — not available yet"
            disabled
          >
            <Bell size={23} />
          </button>
        </header>
        <div className="driver-section-label">
          <span>YOUR ASSIGNED TRIPS</span>
        </div>
        <DriverTrips compact />
        {can(identity, "driver_defect.create_own") && <DriverDefect />}
        <div className="driver-shortcuts">
          {[
            [Navigation, "Navigate"],
            [Phone, "Call Dispatcher"],
            [TriangleAlert, "Report Problem"],
          ].map(([Icon, label]) => {
            const Glyph = Icon as typeof Navigation;
            return (
              <button key={String(label)} disabled>
                <Glyph size={22} />
                <span>{String(label)}</span>
              </button>
            );
          })}
        </div>
        <div className="driver-safety">
          <ShieldCheck size={20} />
          <span>
            Drive. Deliver. Grow.<small>You move business forward.</small>
          </span>
        </div>
      </div>
    </>
  );
}
