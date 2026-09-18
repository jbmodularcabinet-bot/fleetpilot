"use client";
import { useEffect, useState } from "react";
import type { Identity } from "@fleetpilot/types";
import { fuelEstimate, php } from "@/lib/money";
import { ErrorState } from "@fleetpilot/ui";
import {
  actions,
  establish,
  lastSynced,
  retryTrip,
  discardTrip,
  sync,
  rawOwner,
  owner,
  pendingCount,
  type Action,
} from "@/lib/offline";

export function DriverLocalBoundary({
  children,
}: {
  children: React.ReactNode;
}) {
  const [blocked, setBlocked] = useState(false);
  useEffect(() => {
    let alive = true;
    const check = () =>
      void rawOwner()
        .then(async (o) => {
          if (!o) return;
          try {
            await owner();
            if (alive) setBlocked(false);
          } catch {
            if (alive) setBlocked(true);
          }
        })
        .catch(() => {});
    check();
    const timer = setInterval(check, 15000);
    window.addEventListener("fleetpilot-sync", check);
    return () => {
      alive = false;
      clearInterval(timer);
      window.removeEventListener("fleetpilot-sync", check);
    };
  }, []);
  return blocked ? (
    <div className="driver-content">
      <ErrorState message="Saved work is locked. Reconnect and sign in with the same account to continue." />
      <a href="/login?expired=1">Sign in to continue</a>
    </div>
  ) : (
    children
  );
}

export function OfflineStatus({ identity }: { identity?: Identity }) {
  const [offline, setOffline] = useState(false),
    [loaded, setLoaded] = useState(false),
    [rows, setRows] = useState<Action[]>([]),
    [last, setLast] = useState<string>(),
    [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let retryDelay = 1000;

    const scheduleRetry = () => {
      if (!alive || !navigator.onLine || retryTimer) return;
      const delay = retryDelay;
      retryDelay = Math.min(retryDelay * 2, 10000);
      retryTimer = setTimeout(() => {
        retryTimer = undefined;
        void run();
      }, delay);
    };

    async function refresh(): Promise<Action[]> {
      if (!alive) return [];
      setOffline(!navigator.onLine);
      try {
        const a = await actions();
        if (alive) {
          setRows(a);
          setLoaded(true);
        }
        const stamp = await lastSynced();
        if (alive) setLast(stamp);
        return a;
      } catch (e) {
        if (alive) setError((e as Error).message);
        return [];
      }
    }

    async function run() {
      try {
        if (navigator.onLine) {
          if (identity) await establish(identity);
          await sync();
        }
        if (alive) setError("");
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
      const queued = await refresh();
      if (
        alive &&
        navigator.onLine &&
        queued.some((a) => a.status === "PENDING" || a.status === "SYNCING")
      )
        scheduleRetry();
      else retryDelay = 1000;
    }

    const wentOffline = () => {
      if (retryTimer) clearTimeout(retryTimer);
      retryTimer = undefined;
      retryDelay = 1000;
      void refresh();
    };

    if ("serviceWorker" in navigator)
      void navigator.serviceWorker
        .register("/driver-worker.js", { scope: "/driver" })
        .catch(() =>
          setError(
            "Offline shell could not be prepared. Keep the app online and retry.",
          ),
        );
    const tick = setInterval(() => {
      if (document.visibilityState === "visible")
        void pendingCount()
          .then((n) => {
            if (n) void run();
          })
          .catch(() => {});
    }, 30000);
    const channel =
      typeof BroadcastChannel !== "undefined"
        ? new BroadcastChannel("fleetpilot-driver-sync")
        : undefined;
    channel?.addEventListener("message", refresh);
    window.addEventListener("online", run);
    window.addEventListener("focus", run);
    window.addEventListener("offline", wentOffline);
    window.addEventListener("fleetpilot-sync", refresh);
    navigator.serviceWorker?.addEventListener("message", refresh);
    // Offline navigation must be a document request so the public fallback shell can boot.
    const navigate = (event: MouseEvent) => {
      const link = (event.target as HTMLElement).closest("a");
      if (!navigator.onLine && link?.pathname.startsWith("/driver")) {
        event.preventDefault();
        event.stopPropagation();
        window.location.assign(link.href);
      }
    };
    document.addEventListener("click", navigate, true);
    void refresh();
    void run();
    return () => {
      alive = false;
      if (retryTimer) clearTimeout(retryTimer);
      clearInterval(tick);
      channel?.removeEventListener("message", refresh);
      channel?.close();
      window.removeEventListener("online", run);
      window.removeEventListener("focus", run);
      window.removeEventListener("offline", wentOffline);
      window.removeEventListener("fleetpilot-sync", refresh);
      navigator.serviceWorker?.removeEventListener("message", refresh);
      document.removeEventListener("click", navigate, true);
    };
  }, [identity]);
  const pending = rows.filter((a) => a.status !== "SYNCED");
  return (
    <div className="driver-content" aria-label="Connection and sync status">
      <p role="status" className="small muted">
        {!loaded
          ? "Checking saved work…"
          : offline
            ? pending.length
              ? `Offline · ${pending.length} actions saved locally · saved work stays on this device`
              : "Offline · no pending actions"
            : pending.some((a) => a.status === "SYNCING")
              ? "Syncing saved work…"
              : pending.length
                ? `${pending.length} actions saved locally · waiting to sync`
                : "Synced · no pending actions"}
        {last && ` · Last synced ${new Date(last).toLocaleString()}`}
      </p>
      {!!rows.length && (
        <details className="small muted">
          <summary>Saved work ({rows.length})</summary>
          <ul>
            {rows.slice(-20).map((a) => (
              <li key={a.id}>
                <a
                  href={
                    a.command.startsWith("defect")
                      ? "/driver"
                      : `/driver/trips/${a.trip}`
                  }
                >
                  {a.command === "defect"
                    ? "Vehicle defect report"
                    : a.command === "defect_evidence"
                      ? `Defect photo: ${a.filename}`
                      : a.command === "transition"
                        ? String(a.payload.action).replaceAll("_", " ")
                        : a.command === "evidence"
                          ? "Delivery evidence"
                          : a.command === "attempt"
                            ? "Delivery attempt"
                            : a.command === "pod"
                              ? "Proof of delivery"
                              : a.command === "expense"
                                ? `${String(a.payload.category).replaceAll("_", " ")} · ${php(a.payload.category === "FUEL" ? (fuelEstimate(String(a.payload.liters), String(a.payload.price_per_liter)) ?? "") : String(a.payload.amount))}`
                                : a.command === "expense_evidence"
                                  ? `Receipt: ${a.filename}`
                                  : "Delivery issue"}
                </a>{" "}
                ·{" "}
                {a.status === "SYNCED"
                  ? "Synced"
                  : a.status === "SYNCING"
                    ? "Syncing"
                    : a.status === "PENDING"
                      ? "Saved locally"
                      : "Needs attention"}
              </li>
            ))}
          </ul>
        </details>
      )}
      {error && <ErrorState message={error} />}
      {!!pending.length && (
        <button
          className="button secondary"
          onClick={() => void sync().catch((e) => setError(e.message))}
        >
          Retry sync
        </button>
      )}
      {Array.from(
        new Set(
          pending
            .filter((a) => a.status === "FAILED" || a.status === "CONFLICTED")
            .map((a) => a.trip),
        ),
      ).map((trip) => (
        <div key={trip} className="trip-notice">
          <p role="alert">
            Needs attention. The trip changed or this saved action could not be
            accepted. Check with your operator before discarding work.
          </p>
          <button
            className="button secondary"
            onClick={() =>
              void retryTrip(trip).catch((e) => setError(e.message))
            }
          >
            Retry saved work
          </button>
          <button
            className="button secondary"
            onClick={() => {
              if (
                window.confirm(
                  "Discard unsynced work for this trip? Accepted server history remains unchanged.",
                )
              )
                void discardTrip(trip).catch((e) => setError(e.message));
            }}
          >
            Discard unsynced trip work
          </button>
        </div>
      ))}
    </div>
  );
}
