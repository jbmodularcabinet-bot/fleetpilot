import { describe, expect, it, vi } from "vitest";
import Dashboard from "@/app/(owner)/dashboard/page";
import Intelligence from "@/app/(owner)/intelligence/page";
import Report from "@/app/(owner)/reports/[report]/page";
vi.mock("@/lib/server", () => ({
  getIdentity: async () => ({ organization: { id: "org-a" } }),
}));
vi.mock("@/components/mvp1-intelligence", () => ({
  ReportingWorkspace: () => null,
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("Not found");
  },
}));
const initial = {
  dataset: "synthetic",
  date_from: "2026-09-21",
  date_to: "2026-09-24",
};
const selected = {
  ...initial,
  trip_id: "7abd2431-ae5c-4a27-af2c-dd5f02e04316",
};
describe("Report query-navigation isolation", () => {
  it("remounts trip-report state for an authorized same-route drill-down", async () => {
    const list = await Report({
      params: Promise.resolve({ report: "trip-contribution" }),
      searchParams: Promise.resolve(initial),
    });
    const trip = await Report({
      params: Promise.resolve({ report: "trip-contribution" }),
      searchParams: Promise.resolve(selected),
    });
    const same = await Report({
      params: Promise.resolve({ report: "trip-contribution" }),
      searchParams: Promise.resolve({ ...selected }),
    });
    expect(trip.key).not.toBe(list.key);
    expect(same.key).toBe(trip.key);
    expect(trip.props.initialFilters.trip_id).toBe(selected.trip_id);
  });
  it("remounts dashboard state when navigation changes the selected period", async () => {
    const first = await Dashboard({ searchParams: Promise.resolve(initial) });
    const next = await Dashboard({
      searchParams: Promise.resolve({ ...initial, date_from: "2026-09-23" }),
    });
    expect(first.key).not.toBe(next.key);
    expect(next.props.initialFilters.date_from).toBe("2026-09-23");
  });
  it("remounts intelligence state when navigation changes financial status", async () => {
    const all = await Intelligence({ searchParams: Promise.resolve(initial) });
    const final = await Intelligence({
      searchParams: Promise.resolve({ ...initial, financial_status: "FINAL" }),
    });
    expect(all.key).not.toBe(final.key);
    expect(final.props.initialFilters.financial_status).toBe("FINAL");
  });
});
