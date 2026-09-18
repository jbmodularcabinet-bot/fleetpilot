"use client";
import { useEffect, useState } from "react";
import type { Identity } from "@fleetpilot/types";
import { ErrorState, LoadingState } from "@fleetpilot/ui";
import { owner } from "@/lib/offline";
import { MobileBottomNav, Logout } from "./navigation";
import { OfflineStatus, DriverLocalBoundary } from "./offline-status";
import { DriverHomeContent } from "./driver-home";
import { DriverTrips, TripDetail } from "./trips";

export function OfflineShell() {
  const [identity, setIdentity] = useState<Identity>(),
    [error, setError] = useState(""),
    [path, setPath] = useState("");
  useEffect(() => {
    void owner()
      .then((o) => {
        setPath(window.location.pathname);
        setIdentity(o.identity);
      })
      .catch((e) => setError(e.message));
  }, []);
  return (
    <div className="driver-surround">
      <div className="driver-app">
        <main id="main">
          {error ? (
            <div className="driver-content">
              <ErrorState message={error} />
              <a href="/login">Sign in when connected</a>
            </div>
          ) : !identity ? (
            <LoadingState />
          ) : (
            <DriverLocalBoundary>
              <OfflineStatus />
              {/^\/driver\/trips\/[a-f0-9-]+$/.test(path) ? (
                <TripDetail
                  id={path.split("/").pop()!}
                  identity={identity}
                  own
                />
              ) : path === "/driver/trips" ? (
                <DriverTrips />
              ) : path === "/driver/profile" ? (
                <div className="driver-content">
                  <h1>Profile</h1>
                  <p>{identity.user.name}</p>
                  <p className="trip-notice">
                    Reconnect to refresh your profile.
                  </p>
                  <Logout />
                </div>
              ) : (
                <DriverHomeContent identity={identity} />
              )}
            </DriverLocalBoundary>
          )}
        </main>
        <MobileBottomNav />
      </div>
    </div>
  );
}
