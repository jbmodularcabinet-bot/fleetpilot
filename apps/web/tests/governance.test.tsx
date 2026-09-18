import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  AdvanceSummary,
  ReviewChecklist,
  GovernancePanel,
  type Advance,
  type ReviewState,
} from "../src/components/governance";
import type { Identity } from "@fleetpilot/types";
import { request } from "@/lib/client";
vi.mock("@/lib/client", () => ({ request: vi.fn() }));
const ready: ReviewState = {
  status: "READY_FOR_REVIEW",
  blockers: [],
  latest_event_id: null,
  history: [],
};
const identity = {
  permissions: [
    "cash_advance.read",
    "cash_advance.create",
    "cash_advance.settle",
    "cash_advance.void",
    "financial_review.read",
    "financial_review.approve",
  ],
} as Identity;
beforeEach(() => {
  vi.mocked(request).mockImplementation(async (path: string) =>
    path.includes("financial-review") ? ready : { items: [], total: 0 },
  );
});
describe("cash settlement and explicit approval", () => {
  it("renders exact server balances without counting advance as an expense", () => {
    render(
      <AdvanceSummary
        value={
          {
            id: "a",
            amount_issued: "5000.00",
            applied: "3200.00",
            returned: "1800.00",
            outstanding: "0.00",
            status: "SETTLED",
            issued_at: "2030-01-01T00:00:00Z",
            history: [],
          } as Advance
        }
      />,
    );
    expect(screen.getByText("₱5,000.00")).toBeInTheDocument();
    expect(screen.getByText("₱3,200.00")).toBeInTheDocument();
    expect(screen.getByText("₱0.00")).toBeInTheDocument();
  });
  it("shows the explicit blocking reason", () => {
    render(
      <ReviewChecklist
        value={{
          ...ready,
          status: "NEEDS_ATTENTION",
          blockers: ["Cash advance remains outstanding."],
        }}
      />,
    );
    expect(
      screen.getByText("Cash advance remains outstanding."),
    ).toBeInTheDocument();
  });
  it("requires a separate review confirmation and disables blocked approval", async () => {
    vi.mocked(request).mockImplementation(async (path: string) =>
      path.includes("financial-review")
        ? {
            ...ready,
            status: "NEEDS_ATTENTION",
            blockers: ["Cash advance remains outstanding."],
          }
        : { items: [], total: 0 },
    );
    render(
      <GovernancePanel
        tripId="trip"
        identity={identity}
        revision="0"
        onChange={() => {}}
      />,
    );
    const approve = await screen.findByRole("button", {
      name: "Approve financial review",
    });
    expect(approve).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/I have checked revenue/));
    expect(approve).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Review financials" }),
    ).toBeEnabled();
  });
  it("validates money and permanent entry before posting", async () => {
    render(
      <GovernancePanel
        tripId="trip"
        identity={identity}
        revision="0"
        onChange={() => {}}
      />,
    );
    await screen.findByText("No cash advances recorded.");
    fireEvent.click(screen.getByRole("button", { name: "Issue cash advance" }));
    fireEvent.change(screen.getByLabelText("Cash amount (PHP)"), {
      target: { value: "1e3" },
    });
    fireEvent.click(screen.getByLabelText(/I confirm this permanent/));
    fireEvent.click(
      screen.getByRole("button", { name: "Save settlement entry" }),
    );
    expect(
      await screen.findByText(/Enter a positive PHP amount/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Approve financial review" }),
    ).toBeDisabled();
  });
  it("preserves native empty and error recovery states", async () => {
    vi.mocked(request).mockRejectedValueOnce(
      new Error("Connection unavailable"),
    );
    render(
      <GovernancePanel
        tripId="trip"
        identity={identity}
        revision="0"
        onChange={() => {}}
      />,
    );
    expect(
      await screen.findByText("Connection unavailable"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reload settlement" }));
    expect(
      await screen.findByText("No cash advances recorded."),
    ).toBeInTheDocument();
  });
});
