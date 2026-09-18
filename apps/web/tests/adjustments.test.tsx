import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  Adjustments,
  validReason,
  adjustmentValue,
} from "../src/components/adjustments";
import type { Identity } from "@fleetpilot/types";
vi.mock("@/lib/client", () => ({
  request: vi.fn(async (path: string) =>
    path.includes("/expenses/")
      ? {
          effective: { amount: "300.00", sequence: 0, voided: false },
          current: { amount: "300.00" },
        }
      : { items: [], total: 0 },
  ),
}));
describe("closed-trip administrative controls", () => {
  it.each(["", "     ", "a b c d e", "short"])(
    "rejects insufficient reason %s",
    (s) => expect(validReason(s)).toBe(false),
  );
  it("preserves exact centavo display and explicit empty/void values", () => {
    expect(adjustmentValue("10000000.01", "amount")).toBe("₱10,000,000.01");
    expect(adjustmentValue(null, "reference_number")).toBe("Not recorded");
    expect(adjustmentValue(true, "voided")).toBe("true");
    expect(validReason("Receipt verified after trip close.")).toBe(true);
  });
  it("requires confirmation and retains existing form classes", async () => {
    const identity = {
      permissions: [
        "closed_trip_adjustments.read",
        "closed_trip_adjustments.create",
      ],
    } as Identity;
    render(
      <Adjustments
        tripId="trip"
        identity={identity}
        expenses={[{ id: "cost", category: "TOLL", amount: "300.00" }]}
        onChanged={vi.fn()}
      />,
    );
    expect(
      await screen.findByText("No administrative adjustments."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create adjustment" }));
    expect(
      screen.getByRole("button", { name: "Apply adjustment" }),
    ).toBeDisabled();
    expect(screen.getByLabelText(/This will not overwrite/)).toBeRequired();
    expect(screen.getByLabelText("Adjustment reason")).toBeRequired();
    expect(
      screen.getByRole("button", { name: "Apply adjustment" }).closest("form"),
    ).toHaveClass("master-form");
  });
});
