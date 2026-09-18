import { describe, expect, it } from "vitest";
import { formPayload, recordName } from "../src/lib/master-data";
describe("master data form boundaries", () => {
  it("serializes only declared business fields", () => {
    const payload = formPayload("customers", {
      customer_code: " ACME ",
      company_name: " ACME Logistics ",
      organization_id: "foreign",
      created_by: "attacker",
      status: "ACTIVE",
    });
    expect(payload.customer_code).toBe("ACME");
    expect(payload.company_name).toBe("ACME Logistics");
    expect(payload).not.toHaveProperty("organization_id");
    expect(payload).not.toHaveProperty("created_by");
    expect(payload).not.toHaveProperty("status");
  });
  it("preserves zero capacity and normalizes blank optional fields", () => {
    const payload = formPayload("vehicles", {
      unit_number: "TRK-001",
      plate_number: "ABC-1234",
      vehicle_type: "Van",
      capacity: "0",
      capacity_unit: "kg",
      odometer: "0",
    });
    expect(payload.capacity).toBe(0);
    expect(payload.odometer).toBe(0);
    expect(payload.registration_expiry).toBeNull();
  });
  it("uses explicit profile names without needing an identity", () => {
    expect(
      recordName("drivers", {
        id: "driver",
        first_name: "Juan",
        last_name: "Dela Cruz",
        user_id: null,
      }),
    ).toBe("Juan Dela Cruz");
  });
});
