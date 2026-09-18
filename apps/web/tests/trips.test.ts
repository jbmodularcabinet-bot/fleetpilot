import { describe, it, expect } from "vitest";
import { tripPayload, localInput } from "../src/lib/trips";
describe("trip form boundaries", () => {
  it("excludes state, actor and assignment fields from metadata editing", () => {
    const payload = tripPayload({
      pickup_name: " Warehouse A ",
      current_status: "COMPLETED",
      vehicle_id: "other",
      organization_id: "foreign",
      completed_at: "2030-01-01",
    });
    expect(payload.pickup_name).toBe("Warehouse A");
    for (const key of [
      "current_status",
      "vehicle_id",
      "organization_id",
      "completed_at",
    ])
      expect(payload).not.toHaveProperty(key);
  });
  it("sends explicit instants and preserves zero numeric values", () => {
    const payload = tripPayload({
      scheduled_pickup_at: "2030-01-10T08:00",
      cargo_weight: "0",
      cargo_weight_unit: "kg",
      pickup_latitude: "0",
      pickup_longitude: "0",
    });
    expect(payload.scheduled_pickup_at).toBe(
      new Date("2030-01-10T08:00").toISOString(),
    );
    expect(payload.cargo_weight).toBe(0);
    expect(payload.pickup_latitude).toBe(0);
    expect(payload.scheduled_delivery_at).toBeNull();
  });
  it("round-trips datetime input without changing the scheduled instant", () => {
    const instant = "2030-01-10T08:00:00Z";
    expect(new Date(localInput(instant)).toISOString()).toBe(
      new Date(instant).toISOString(),
    );
    expect(localInput(null)).toBe("");
  });
});
