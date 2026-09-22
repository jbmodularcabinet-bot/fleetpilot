import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Identity } from "@fleetpilot/types";
import { reportingEntryFilters } from "@/lib/reporting-server";
vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({
  cookies: async () => ({ toString: () => "test-session-cookie" }),
}));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(path);
  },
}));
const identity = {
  organization: { id: "tenant-a" },
  permissions: [
    "trip_financials.read",
    "trip_profitability.read",
    "expenses.read",
    "fuel.read",
    "cash_advance.read",
    "financial_review.read",
  ],
} as Identity;
const defaults = {
  dataset: "synthetic",
  date_from: "2026-09-21",
  date_to: "2026-09-24",
};
const response = (value: unknown, status = 200) => ({
  ok: status === 200,
  status,
  json: async () => value,
});
beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
afterEach(() => vi.unstubAllGlobals());
describe("Client-demo entry defaults", () => {
  it("loads authorized sample data on a bare route", async () => {
    vi.mocked(fetch).mockResolvedValue(
      response({
        organization_id: "tenant-a",
        available: true,
        trip_count: 4,
        filters: defaults,
      }) as Response,
    );
    expect(await reportingEntryFilters(identity, {})).toEqual(defaults);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/reports/demo-context"),
      expect.objectContaining({ cache: "no-store" }),
    );
  });
  it.each<Record<string, string>>([
    { dataset: "business" },
    { date_from: "2026-09-01" },
    { financial_status: "FINAL" },
    defaults,
  ])("does not replace explicit filters: %j", async (filters) => {
    expect(await reportingEntryFilters(identity, filters)).toEqual(filters);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("keeps a normal business workspace unchanged", async () => {
    vi.mocked(fetch).mockResolvedValue(
      response({
        organization_id: "tenant-a",
        available: false,
        filters: {},
      }) as Response,
    );
    expect(await reportingEntryFilters(identity, {})).toEqual({});
  });
  it("never requests sample context for a user denied expense visibility", async () => {
    const denied = {
      ...identity,
      permissions: identity.permissions.filter((p) => p !== "expenses.read"),
    };
    expect(await reportingEntryFilters(denied, {})).toEqual({});
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([401, 403, 409, 503])(
    "does not turn context error %s into a zero report",
    async (status) => {
      vi.mocked(fetch).mockResolvedValue(response({}, status) as Response);
      await expect(reportingEntryFilters(identity, {})).rejects.toThrow();
    },
  );
  it("rejects mismatched tenant context", async () => {
    vi.mocked(fetch).mockResolvedValue(
      response({
        organization_id: "tenant-b",
        available: true,
        trip_count: 4,
        filters: defaults,
      }) as Response,
    );
    await expect(reportingEntryFilters(identity, {})).rejects.toThrow(
      "identity",
    );
  });
});
