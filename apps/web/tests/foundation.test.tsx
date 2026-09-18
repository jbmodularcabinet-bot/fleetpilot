import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DriverPrimaryAction, EmptyState, KpiCard } from "@fleetpilot/ui";
import { can, homeFor } from "@fleetpilot/auth";
import type { Identity, Permission } from "@fleetpilot/types";

function identity(permissions: Permission[]): Identity {
  return { permissions } as Identity;
}
describe("Foundation shells", () => {
  it("shows absent KPI values without pretending to have metrics", () => {
    render(<KpiCard label="Revenue Today" icon={<span />} />);
    expect(screen.getByLabelText("No data")).toHaveTextContent("—");
    expect(screen.queryByText(/2,489/)).not.toBeInTheDocument();
  });
  it("does not allow a driver to start an unimplemented trip", () => {
    render(<DriverPrimaryAction />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
  it("explains empty content", () => {
    render(
      <EmptyState
        title="No trip connected"
        description="Your next assignment will be shown here."
      />,
    );
    expect(screen.getByRole("heading")).toHaveTextContent("No trip connected");
  });
  it("routes roles using server supplied permissions", () => {
    expect(homeFor(identity(["owner_dashboard.view"]))).toBe("/dashboard");
    expect(homeFor(identity(["driver_app.view"]))).toBe("/driver");
    expect(homeFor(identity(["organization.read"]))).toBe(
      "/settings/organization",
    );
    expect(can(identity(["driver_app.view"]), "users.manage")).toBe(false);
  });
});
