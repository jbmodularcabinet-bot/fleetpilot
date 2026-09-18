import { defineConfig } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
// Isolated test environment, never developer accounts or production data.
const entries = readFileSync(".runtime/test.env", "utf8")
  .split(/\r?\n/)
  .filter((line) => line.includes("="))
  .map((line) => [
    line.slice(0, line.indexOf("=")),
    line.slice(line.indexOf("=") + 1),
  ]);
const testEnv = Object.fromEntries(entries);
if (!testEnv.DATABASE_URL?.endsWith("/fleetpilot_test"))
  throw new Error("E2E requires isolated fleetpilot_test database");
process.env.DEMO_PASSWORD = testEnv.DEMO_PASSWORD;
const productionSmoke = process.env.FLEETPILOT_PRODUCTION_SMOKE === "1";
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45000,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3100",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    browserName: "chromium",
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
  },
  webServer: [
    {
      command: `"${resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python")}" -m uvicorn fleetpilot.main:app --host 127.0.0.1 --port 8100`,
      cwd: resolve("apps/api"),
      url: "http://127.0.0.1:8100/health",
      reuseExistingServer: false,
      env: {
        ...testEnv,
        WEB_ORIGIN: "http://localhost:3100",
        LOGIN_LIMIT: "100",
        MUTATION_LIMIT: "1000",
        UPLOAD_LIMIT: "200",
        EVIDENCE_ACCESS_LIMIT: "500",
      },
    },
    {
      command: productionSmoke
        ? `node "${resolve("scripts/start-production-web.mjs")}"`
        : `node "${resolve("node_modules/next/dist/bin/next")}" dev --hostname 127.0.0.1 --port 3100`,
      cwd: resolve("apps/web"),
      url: "http://localhost:3100/login",
      reuseExistingServer: false,
      timeout: 120000,
      env: {
        API_INTERNAL_URL: "http://127.0.0.1:8100",
        FLEETPILOT_E2E: productionSmoke ? "0" : "1",
      },
    },
  ],
});
