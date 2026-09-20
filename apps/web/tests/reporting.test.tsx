import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import type { Identity } from "@fleetpilot/types";
import type { ReportData, Summary } from "@/lib/reporting";
import { ContributionMetrics } from "@/components/reporting-views";
import { ReportingWorkspace } from "@/components/mvp1-intelligence";
vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/components/financials", () => ({
  FinancialPanel: () => <div>Existing financial source panel</div>,
}));
const summary: Summary = {
  revenue: "74000.00",
  direct_cost: "40250.00",
  contribution: "33750.00",
  weighted_margin_percent: "45.61",
  trip_count: 4,
  positive_count: 3,
  negative_count: 1,
  zero_count: 0,
  insufficient_data_count: 0,
  final_count: 0,
  provisional_count: 4,
  attention_trip_count: 4,
};
const identity = {
  user: { id: "owner", name: "Owner" },
  membership: { role: "OWNER" },
  organization: {
    id: "org-a",
    name: "Synthetic Logistics",
    timezone: "Asia/Manila",
  },
  permissions: [
    "trip_financials.read",
    "trip_profitability.read",
    "expenses.read",
    "fuel.read",
    "cash_advance.read",
    "financial_review.read",
  ],
} as Identity;
function payload(): ReportData {
  return {
    report: "executive-contribution",
    title: "Executive Contribution",
    scope: {
      organization_id: "org-a",
      organization_name: "Synthetic Logistics",
      date_from: "2026-09-21",
      date_to: "2026-09-24",
      timezone: "Asia/Manila",
      date_basis: "Scheduled pickup date",
      lifecycle: "ALL",
      financial_status: "ALL",
      record_count: 4,
      calculated_at: "2026-09-20T12:00:00Z",
      rule_version: "v1",
      fingerprint: "test",
      qualification: "Contribution is not net profit or cash collected.",
      warnings: ["All four trips remain provisional"],
      synthetic: true,
      demo_available: true,
      dataset: "synthetic",
      customer_id: null,
      vehicle_id: null,
      trip_id: null,
    },
    summary,
    owner_brief: ["Four synthetic trips have reviewed source inputs."],
    policy: {},
    advance_summary: {
      captured_amount: "5000.00",
      issued: "0.00",
      outstanding: "0.00",
      unreconciled_capture_count: 1,
    },
    category_summary: [],
    top_customers: [],
    priority_findings: [],
    finding_count: 0,
    recent_changes: [],
    history_available: true,
    lifecycle_totals: [],
    filter_options: { customers: [], vehicles: [] },
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  };
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("Contribution reporting UI", () => {
  it("formats authoritative values without computing new financial totals", () => {
    render(<ContributionMetrics value={summary} />);
    expect(screen.getByTestId("Contribution")).toHaveTextContent("₱33,750.00");
    expect(
      screen.getByTestId("Weighted Contribution Margin"),
    ).toHaveTextContent("45.61%");
    expect(screen.getByTestId("Negative-Contribution Trips")).toHaveTextContent(
      "1",
    );
  });
  it("preserves loss and N/A instead of clamping", () => {
    render(
      <ContributionMetrics
        value={{
          ...summary,
          contribution: "-1200.00",
          weighted_margin_percent: null,
        }}
      />,
    );
    expect(screen.getByTestId("Contribution")).toHaveTextContent("−₱1,200.00");
    expect(
      screen.getByTestId("Weighted Contribution Margin"),
    ).toHaveTextContent("N/A");
  });
  it("does not request financial data when expense visibility is denied", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    render(
      <ReportingWorkspace
        identity={{
          ...identity,
          permissions: identity.permissions.filter(
            (p) => p !== "expenses.read",
          ),
        }}
        mode="dashboard"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Costs or settlement balances will not be replaced by zero",
    );
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("shows request errors instead of zero-valued business metrics", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          status: 503,
          json: async () => ({
            error: { message: "Financial records are busy" },
          }),
        }),
    );
    render(<ReportingWorkspace identity={identity} mode="dashboard" />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Financial records are busy",
    );
    expect(screen.queryByTestId("Contribution")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry report" })).toBeEnabled();
  });
  it("requests no-store and clearly labels the synthetic period", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => payload(),
      });
    vi.stubGlobal("fetch", fetcher);
    render(
      <ReportingWorkspace
        identity={identity}
        mode="dashboard"
        initialFilters={{
          dataset: "synthetic",
          date_from: "2026-09-21",
          date_to: "2026-09-24",
        }}
      />,
    );
    expect(await screen.findByTestId("Contribution")).toHaveTextContent(
      "₱33,750.00",
    );
    expect(screen.getByText("SYNTHETIC VALIDATION DATA")).toBeVisible();
    expect(
      screen.getByText(/not verified deliveries completed today/),
    ).toBeVisible();
    expect(fetcher.mock.calls[0][1].cache).toBe("no-store");
    expect(fetcher.mock.calls[0][0]).toContain("dataset=synthetic");
  });
  it("removes previous-organization values while the next report loads", async () => {
    let complete: ((value: unknown) => void) | undefined;
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => payload(),
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            complete = resolve;
          }),
      );
    vi.stubGlobal("fetch", fetcher);
    const view = render(
      <ReportingWorkspace identity={identity} mode="dashboard" />,
    );
    await screen.findByTestId("Contribution");
    view.rerender(
      <ReportingWorkspace
        identity={{
          ...identity,
          organization: { ...identity.organization, id: "org-b" },
        }}
        mode="dashboard"
      />,
    );
    expect(screen.queryByTestId("Contribution")).not.toBeInTheDocument();
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    await act(async () => {
      complete?.({
        ok: false,
        status: 403,
        json: async () => ({
          error: { message: "Access denied in selected organization" },
        }),
      });
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Access denied");
  });
});
