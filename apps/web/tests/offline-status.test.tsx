import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { OfflineStatus } from "../src/components/offline-status";
import {
  actions,
  lastSynced,
  pendingCount,
  type Action,
} from "../src/lib/offline";

vi.mock("../src/lib/offline", () => ({
  actions: vi.fn(),
  lastSynced: vi.fn(),
  pendingCount: vi.fn(),
  sync: vi.fn(),
  establish: vi.fn(),
  rawOwner: vi.fn(),
  owner: vi.fn(),
  retryTrip: vi.fn(),
  discardTrip: vi.fn(),
}));
beforeEach(() => {
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    value: false,
  });
  vi.mocked(lastSynced).mockResolvedValue(undefined);
  vi.mocked(pendingCount).mockResolvedValue(0);
});
afterEach(() => {
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    value: true,
  });
});
it("does not acknowledge a local save while the offline queue is empty", async () => {
  vi.mocked(actions).mockResolvedValue([]);
  render(<OfflineStatus />);
  expect(await screen.findByText("Offline · no pending actions")).toBeVisible();
  expect(screen.queryByText(/actions saved locally/)).not.toBeInTheDocument();
});
it("acknowledges a saved action returned from durable storage", async () => {
  vi.mocked(actions).mockResolvedValue([
    {
      id: "saved",
      owner: "org:user:driver",
      trip: "trip",
      command: "expense",
      payload: { category: "TOLL", amount: "350.00" },
      expected_version: 2,
      captured: "2026-09-17T00:00:00Z",
      sequence: 1,
      status: "PENDING",
      retries: 0,
    } satisfies Action,
  ]);
  render(<OfflineStatus />);
  expect(
    await screen.findByText(
      "Offline · 1 actions saved locally · saved work stays on this device",
    ),
  ).toBeVisible();
});
