import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { Identity } from "@fleetpilot/types";
import { LegacyReviewQueue } from "../src/components/financials";
import { GovernancePanel, type ReviewState } from "../src/components/governance";
import { request } from "@/lib/client";

vi.mock("@/lib/client", () => ({ request: vi.fn() }));

const identity = {
  permissions: [
    "cash_advance.read",
    "financial_review.read",
    "financial_review.approve",
  ],
} as Identity;

const review: ReviewState = {
  status: "NEEDS_ATTENTION",
  blockers: ["Direct expenses await review."],
  latest_event_id: null,
  history: [],
  legacy_expenses: [
    {
      id: "expense-1",
      category: "PARKING",
      amount: "200.00",
      original_amount: "200.00",
      occurred_at: "2030-01-01T00:00:00Z",
      description: "Legacy parking",
      first_name: "Juan",
      last_name: "Dela Cruz",
    },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.mocked(request).mockImplementation(async (path: string) => {
    if (path === "/financial-review/legacy")
      return {
        items: [
          {
            id: "trip-1",
            trip_number: "TRIP-001",
            completed_at: "2030-01-02T00:00:00Z",
            company_name: "ACME Logistics Client",
            unreviewed_expenses: 3,
            financials: { contribution_amount: "15350.00", status: "PROVISIONAL" },
          },
        ],
      } as never;
    if (path.includes("financial-review")) return review as never;
    if (path.includes("cash-advances")) return { items: [], total: 0 } as never;
    if (path.includes("expenses")) return { items: [], total: 0 } as never;
    throw new Error(`Unexpected request ${path}`);
  });
});

describe("legacy closed-trip financial review", () => {
  it("renders the owner review queue using the locked component system", async () => {
    render(<LegacyReviewQueue identity={identity} />);
    expect(await screen.findByText(/TRIP-001/)).toBeInTheDocument();
    expect(screen.getByText(/3.*expense records need review/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review trip" })).toHaveAttribute("href", "/trips/trip-1");
  });

  it("shows immutable legacy blockers and posts explicit acceptance", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ outcome: "APPLIED", result: { review } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<GovernancePanel tripId="trip-1" identity={identity} revision="0" onChange={() => {}} />);
    expect(await screen.findByText("Financial review blockers")).toBeInTheDocument();
    expect(screen.getByText(/Parking/)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Accept legacy expense" }));
    });
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/expenses/expense-1/legacy-review",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });
});
