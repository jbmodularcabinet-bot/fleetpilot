import { describe, expect, it } from "vitest";
import { project, ownerKey, type Action, type Owner } from "../src/lib/offline";
import type { TripRecord } from "../src/lib/trips";

const trip = {
  id: "trip-a",
  version: 2,
  current_status: "DISPATCHED",
  current_milestone: "DISPATCHED",
  next_action: "start_pickup",
} as TripRecord;
const row = (
  verb: string,
  version: number,
  status: Action["status"] = "PENDING",
) =>
  ({
    id: "command-a",
    owner: "org:user:driver",
    captured: "2026-09-17T00:00:00Z",
    sequence: version,
    retries: 0,
    trip: "trip-a",
    command: "transition",
    expected_version: version,
    payload: { action: verb },
    status,
  }) as Action;
describe("offline projection never replaces authoritative status", () => {
  it("orders captured milestones while leaving status server-confirmed", () => {
    const view = project(trip, [
      row("start_pickup", 2),
      row("arrive_pickup", 3),
    ]);
    expect(view.current_status).toBe("DISPATCHED");
    expect(view.current_milestone).toBe("ARRIVED_PICKUP");
    expect(view.next_action).toBe("start_loading");
    expect(view.version).toBe(4);
    expect(trip.version).toBe(2);
  });
  it("blocks progression at a stale conflict", () => {
    expect(
      project(trip, [row("start_pickup", 2, "CONFLICTED")]).next_action,
    ).toBeNull();
  });
  it("never shows a pending POD as delivered", () => {
    const view = project(trip, [{ ...row("", 2), command: "pod" }]);
    expect(view.current_status).toBe("DISPATCHED");
    expect(view.offline_pending).toBe(true);
  });
  it("ignores another trip and accepted commands", () => {
    expect(
      project(trip, [
        { ...row("start_pickup", 2), trip: "other" },
        row("start_pickup", 2, "SYNCED"),
      ]),
    ).toEqual(trip);
  });
  it("scopes storage by all three ownership identities", () => {
    const a = {
      organization_id: "org",
      user_id: "user",
      driver_id: "driver",
    } as Owner;
    expect(
      new Set([
        ownerKey(a),
        ownerKey({ ...a, user_id: "b" }),
        ownerKey({ ...a, driver_id: "b" }),
        ownerKey({ ...a, organization_id: "b" }),
      ]).size,
    ).toBe(4);
  });
  it("advances stale expense props past a durable expense and its receipt", () => {
    const pending = [
      { ...row("", 2), command: "expense" },
      { ...row("", 3), command: "expense_evidence" },
    ];
    expect(project(trip, pending).version).toBe(4);
    expect(project(project(trip, pending), pending).version).toBe(4);
    expect(trip.version).toBe(2);
  });
  it("does not advance expenses past an unresolved local conflict", () => {
    const pending = [
      { ...row("", 2, "CONFLICTED"), command: "expense" },
      { ...row("", 3), command: "expense_evidence" },
    ];
    expect(project(trip, pending).version).toBe(2);
    expect(project(trip, pending).next_action).toBeNull();
  });
});
