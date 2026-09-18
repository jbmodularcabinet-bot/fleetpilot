import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import {
  DriverDefect,
  VehicleMaintenance,
} from "../src/components/maintenance";
import { project, type Action } from "../src/lib/offline";
import type { TripRecord } from "../src/lib/trips";
import type { Identity } from "@fleetpilot/types";
vi.mock("../src/lib/client", () => ({ request: vi.fn() }));
vi.mock("../src/lib/offline", async (original) => ({
  ...(await original<object>()),
  queueDefect: vi.fn(),
  sync: vi.fn().mockResolvedValue(undefined),
}));
import { request } from "../src/lib/client";
import { queueDefect } from "../src/lib/offline";
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(request).mockResolvedValue({
    items: [{ id: "vehicle", unit_number: "TRK-001" }],
  });
});
describe("maintenance capture", () => {
  it("shows the assigned-vehicle defect form", async () => {
    render(<DriverDefect />);
    fireEvent.click(
      screen.getByRole("button", { name: "Report vehicle issue" }),
    );
    expect(await screen.findByText("TRK-001")).toBeVisible();
    expect(screen.getByLabelText("Defect description")).toBeRequired();
    expect(screen.getByLabelText("Defect photos")).toHaveAttribute("multiple");
  });
  it("acknowledges only successful local persistence", async () => {
    vi.mocked(queueDefect).mockResolvedValue(undefined);
    render(<DriverDefect vehicle="vehicle" />);
    fireEvent.click(screen.getByText("Report vehicle issue"));
    fireEvent.change(screen.getByLabelText("Defect description"), {
      target: { value: "Soft brake pedal" },
    });
    fireEvent.click(screen.getByText("Save vehicle issue"));
    expect(await screen.findByText(/Saved locally. Check sync/)).toBeVisible();
    expect(queueDefect).toHaveBeenCalledOnce();
  });
  it("does not claim saved when persistence fails", async () => {
    vi.mocked(queueDefect).mockRejectedValue(
      new Error("Storage quota exhausted"),
    );
    render(<DriverDefect vehicle="vehicle" />);
    fireEvent.click(screen.getByText("Report vehicle issue"));
    fireEvent.change(screen.getByLabelText("Defect description"), {
      target: { value: "Soft brake pedal" },
    });
    fireEvent.click(screen.getByText("Save vehicle issue"));
    expect(await screen.findByText("Storage quota exhausted")).toBeVisible();
    expect(
      screen.queryByText(/Saved locally. Check sync/),
    ).not.toBeInTheDocument();
  });
  it("does not change trip version for a defect command", () => {
    const trip = {
      id: "trip",
      version: 4,
      current_status: "DISPATCHED",
      next_action: "start_pickup",
    } as TripRecord;
    expect(
      project(trip, [
        {
          trip: "trip",
          command: "defect",
          expected_version: 1,
          status: "PENDING",
        } as Action,
      ]).version,
    ).toBe(4);
  });
  it("uses native maintenance empty state with no fake metrics", async () => {
    vi.mocked(request).mockResolvedValue({
      trusted_odometer: "48000",
      schedules: [],
      work_orders: [],
      defects: [],
    });
    render(
      <VehicleMaintenance
        vehicle="vehicle"
        identity={{ permissions: [] } as unknown as Identity}
      />,
    );
    await waitFor(() =>
      expect(screen.getByText("Trusted odometer: 48000 km")).toBeVisible(),
    );
    expect(screen.getByText("No defect reports.")).toBeVisible();
    expect(screen.queryByText("Create work order")).not.toBeInTheDocument();
  });
});
