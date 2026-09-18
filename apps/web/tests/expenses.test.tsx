import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ExpenseForm } from "../src/components/expenses";
import { fuelEstimate, php, validDecimal } from "../src/lib/money";
import { project, type Action } from "../src/lib/offline";
import type { TripRecord } from "../src/lib/trips";

const trip = {
  id: "trip",
  version: 2,
  current_status: "DISPATCHED",
  current_milestone: "DISPATCHED",
  next_action: "start_pickup",
} as TripRecord;
describe("exact expense display and capture", () => {
  it("rejects invalid local money before queueing while retaining exact boundary values", () => {
    for (const value of [
      "NaN",
      "Infinity",
      "-1",
      "0",
      "1e3",
      "0.001",
      "10000000.01",
    ])
      expect(validDecimal(value, 2, "10000000")).toBe(false);
    for (const value of ["0.01", "1.10", "10000000.00"])
      expect(validDecimal(value, 2, "10000000")).toBe(true);
  });
  it.each([
    ["52.35", "61.75", "3232.61"],
    ["1", "0.005", "0.01"],
    ["0.1", "0.1", "0.01"],
    ["1.001", "1.0001", "1.00"],
  ])("rounds %s × %s with integer arithmetic", (liters, price, total) => {
    expect(fuelEstimate(liters, price)).toBe(total);
  });
  it("formats centavos without Number conversion", () => {
    expect(php("10000000.01")).toBe("₱10,000,000.01");
    expect(fuelEstimate("NaN", "1")).toBeNull();
  });
  it("shows the server recalculation distinction and required OTHER notes", () => {
    render(<ExpenseForm trip={trip} own onDone={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Liters"), {
      target: { value: "52.35" },
    });
    fireEvent.change(screen.getByLabelText("Price per liter (PHP)"), {
      target: { value: "61.75" },
    });
    expect(screen.getByText(/Estimated total: ₱3,232.61/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Expense category"), {
      target: { value: "OTHER" },
    });
    expect(screen.getByLabelText("Expense notes")).toBeRequired();
    expect(screen.getByLabelText("Amount (PHP)")).toBeRequired();
  });
  it("pending expense advances version without changing trip milestone", () => {
    const action = {
      id: "expense-command",
      owner: "org:user:driver",
      captured: "2026-09-17T00:00:00Z",
      sequence: 1,
      retries: 0,
      trip: "trip",
      command: "expense",
      status: "PENDING",
      expected_version: 2,
      payload: { category: "FUEL" },
    } as Action;
    const result = project(trip, [action]);
    expect(result.version).toBe(3);
    expect(result.current_milestone).toBe("DISPATCHED");
    expect(result.next_action).toBe("start_pickup");
    expect(result.offline_pending).toBe(true);
  });
});
