import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { Identity } from "@fleetpilot/types";
import { canReport } from "./reporting";

/** Bare demo entry uses authorized sample dates; explicit business/custom filters win. */
export async function reportingEntryFilters(
  identity: Identity,
  filters: Record<string, string>,
): Promise<Record<string, string>> {
  if (Object.keys(filters).length || !canReport(identity)) return filters;
  const store = await cookies();
  const response = await fetch(
    `${process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000"}/api/v1/reports/demo-context`,
    { headers: { cookie: store.toString() }, cache: "no-store" },
  );
  if (response.status === 401) redirect("/login?expired=1");
  if (response.status === 403) redirect("/access-denied");
  if (!response.ok)
    throw new Error(
      "Demo workspace setup is unavailable. Retry; no zero totals have been substituted.",
    );
  const context = await response.json();
  if (
    context.organization_id !== identity.organization.id ||
    typeof context.available !== "boolean"
  )
    throw new Error("Reporting workspace identity could not be verified.");
  if (!context.available) return filters;
  if (
    context.filters?.dataset !== "synthetic" ||
    !Number.isInteger(context.trip_count) ||
    context.trip_count < 1 ||
    !/^\d{4}-\d{2}-\d{2}$/.test(context.filters.date_from ?? "") ||
    !/^\d{4}-\d{2}-\d{2}$/.test(context.filters.date_to ?? "")
  )
    throw new Error("Sample report period could not be verified.");
  return {
    dataset: "synthetic",
    date_from: context.filters.date_from,
    date_to: context.filters.date_to,
  };
}
