import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { Identity } from "@fleetpilot/types";
import type { TripRecord } from "../src/lib/trips";
import {
  FinancialSummary,
  FinancialPanel,
  type Financial,
} from "../src/components/financials";
import { php } from "../src/lib/money";
const value: Financial = {
  trip_id: "trip",
  currency: "PHP",
  status: "FINAL",
  unreviewed_count: 0,
  revenue: {
    effective_total: "25000.00",
    submitted_total: "25000.00",
    breakdown: [],
  },
  direct_cost: {
    effective_total: "10300.00",
    submitted_total: "10300.00",
    breakdown: [],
  },
  contribution_amount: "14700.00",
  contribution_margin_percent: "58.80",
  excluded_cash_advances: "0.00",
};
vi.mock("@/lib/client", () => ({
  request: vi.fn(async (path: string) =>
    path.endsWith("financials") ? value : { items: [], total: 0 },
  ),
}));
describe("server-authoritative trip contribution", () => {
  it("renders the server response and exclusion policy", () => {
    render(<FinancialSummary value={value} />);
    expect(screen.getByText("₱14,700.00")).toBeInTheDocument();
    expect(screen.getByText("58.80%")).toBeInTheDocument();
    expect(screen.getByText(/Maintenance is excluded/)).toBeInTheDocument();
    expect(screen.getByText("FINAL")).toBeInTheDocument();
  });
  it("renders negative contribution and zero-revenue margin without client arithmetic", () => {
    render(
      <FinancialSummary
        value={{
          ...value,
          contribution_amount: "-2500.00",
          contribution_margin_percent: null,
          status: "PROVISIONAL",
        }}
      />,
    );
    expect(screen.getByText("−₱2,500.00")).toBeInTheDocument();
    expect(screen.getByText("N/A")).toBeInTheDocument();
    expect(php("-0.01")).toBe("−₱0.01");
    expect(php("NaN")).toBe("Unavailable");
  });
  it("validates revenue locally while preserving the approved form", async () => {
    render(
      <FinancialPanel
        trip={
          { id: "trip", version: 1, current_status: "COMPLETED" } as TripRecord
        }
        identity={{ permissions: ["trip_revenue.create"] } as Identity}
        revision={0}
      />,
    );
    await screen.findByText("No revenue recorded yet.");
    fireEvent.click(screen.getByRole("button", { name: "Add revenue" }));
    fireEvent.change(screen.getByLabelText("Revenue amount (PHP)"), {
      target: { value: "1e3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save revenue" }));
    expect(
      await screen.findByText(/Enter a positive PHP amount/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Save revenue" }).closest("form"),
    ).toHaveClass("master-form");
  });
  it("does not expose entry controls without permission", async () => {
    render(
      <FinancialPanel
        trip={
          { id: "trip", version: 1, current_status: "COMPLETED" } as TripRecord
        }
        identity={{ permissions: [] } as unknown as Identity}
        revision={0}
      />,
    );
    await screen.findByText("No revenue recorded yet.");
    expect(
      screen.queryByRole("button", { name: "Add revenue" }),
    ).not.toBeInTheDocument();
  });
});
