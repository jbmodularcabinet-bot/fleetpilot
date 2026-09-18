"use client";
import {
  beforeAccountExit,
  clearOffline,
  rawOwner,
  establish,
} from "@/lib/offline";
import { useState, useSyncExternalStore } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { ErrorState } from "@fleetpilot/ui";
export function LoginForm() {
  const ready = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const params = useSearchParams();
  return (
    <form
      method="post"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        const form = new FormData(e.currentTarget);
        try {
          const local = await rawOwner();
          const same =
            local?.identity.user.email.toLowerCase() ===
            String(form.get("email")).trim().toLowerCase();
          if (!same && !(await beforeAccountExit())) {
            setBusy(false);
            return;
          }
          const response = await fetch("/api/v1/auth/login", {
            method: "POST",
            body: new URLSearchParams({
              username: String(form.get("email")),
              password: String(form.get("password")),
            }),
          });
          if (!response.ok) {
            const data = await response.json();
            throw new Error(
              data.error?.message ?? "Unable to sign in. Please try again.",
            );
          }
          const me = await fetch("/api/v1/me", {
            credentials: "same-origin",
            cache: "no-store",
          });
          if (!me.ok)
            throw new Error("Unable to verify the signed-in account.");
          const identity = await me.json();
          if (
            same &&
            identity.user.id === local?.user_id &&
            identity.organization.id === local?.organization_id &&
            identity.membership.role === "DRIVER"
          )
            await establish(identity);
          else await clearOffline();
          window.location.assign("/");
        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to connect. Please retry.",
          );
          setBusy(false);
        }
      }}
    >
      <fieldset disabled={busy || !ready}>
        {params.has("expired") && (
          <p role="status" className="muted small">
            Your session has expired. Sign in to continue.
          </p>
        )}
        <label>
          Email address
          <input
            type="email"
            name="email"
            autoComplete="username"
            placeholder="you@yourcompany.com"
            required
            maxLength={320}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            placeholder="Enter your password"
            required
            maxLength={128}
          />
        </label>
        {error && <ErrorState message={error} />}
        <button className="button primary login-submit">
          {busy ? "Signing in…" : "Sign in"}
          <ArrowRight size={18} />
        </button>
      </fieldset>
      <noscript>Enable JavaScript to sign in securely.</noscript>
      <p className="small muted login-help">
        Need access? Contact your organization’s administrator.
      </p>
    </form>
  );
}
