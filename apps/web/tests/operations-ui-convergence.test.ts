import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const root = path.resolve(__dirname, "..");
const trips = fs.readFileSync(path.join(root, "src/components/trips.tsx"), "utf8");
const css = fs.readFileSync(path.join(root, "src/app/globals.css"), "utf8");

describe("Operations UI convergence", () => {
  it("shows an explicit no-telemetry Live Fleet state without fabricated positions", () => {
    expect(trips).toContain("Live GPS telemetry is not connected");
    expect(trips).toContain("does not infer truck positions");
    expect(trips).toContain("No fabricated truck positions");
    expect(css).toContain(".operations-map-empty");
  });

  it("preserves dispatch as the verified operational surface", () => {
    expect(trips).toContain('className="master-card dispatch-card"');
    expect(trips).toContain('className="dispatch-table"');
    expect(trips).toContain("Plan assigned work, schedules, drivers and trip status.");
  });

  it("gives owner Trip Detail the approved route and section hierarchy", () => {
    for (const marker of [
      "trip-command-summary",
      "trip-section-nav",
      "trip-overview",
      "trip-tracking",
      "trip-expenses",
      "trip-pod",
      "trip-financial",
      "trip-activity",
    ])
      expect(trips).toContain(marker);
  });
});
