import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const windowsRoot =
  process.platform === "win32"
    ? "C:/Users/User/Documents/ChatGPT/FleetPilot"
    : "/mnt/c/Users/User/Documents/ChatGPT/FleetPilot";
const credentialPath = path.join(
  windowsRoot,
  ".runtime/client-demo-credentials.json",
);
const authorized = JSON.parse(
  await fs.readFile(
    path.join(root, ".runtime/batch16/authorized-demo-origin.json"),
    "utf8",
  ),
);
const base = process.argv[2] ?? authorized.origin;
assert.equal(
  base,
  authorized.origin,
  "Use only the authorized public demo origin",
);

const credential = JSON.parse(await fs.readFile(credentialPath, "utf8"));
assert.equal(credential.email, "client.demo@fleetpilot.ph");
assert(
  typeof credential.password === "string" && credential.password.length >= 16,
);

const { chromium } = await import(
  pathToFileURL(path.join(windowsRoot, "node_modules/playwright/index.mjs"))
    .href
);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
const checks = [];
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
async function check(name, operation) {
  try {
    await operation();
    checks.push({ name, status: "PASS" });
    console.log("PASS " + name);
  } catch (error) {
    checks.push({ name, status: "FAIL", error: error.message });
    console.log("FAIL " + name + ": " + error.message);
  }
}

async function browserRequest(url, init = {}) {
  return page.evaluate(
    async ({ url, init }) => {
      const response = await fetch(url, {
        credentials: "same-origin",
        ...init,
        headers: {
          "Content-Type": "application/json",
          ...(init.headers ?? {}),
        },
      });
      let body;
      try {
        body = await response.json();
      } catch {
        body = null;
      }
      return { status: response.status, body };
    },
    { url, init },
  );
}

await page.goto(base + "/login", { waitUntil: "domcontentloaded" });
await page.getByLabel("Email address").fill(credential.email);
await page.getByLabel("Password", { exact: true }).fill(credential.password);
await page.getByRole("button", { name: "Sign in", exact: true }).click();
await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 30000 });
await check("Read-only identity and exact permissions", async () => {
  const response = await page.request.get(base + "/api/v1/me");
  assert.equal(response.status(), 200);
  const me = await response.json();
  assert.equal(me.membership.access_profile, "CLIENT_DEMO_READONLY");
  assert.deepEqual(
    new Set(me.permissions),
    new Set([
      "organization.read",
      "owner_dashboard.view",
      "trips.read",
      "trip_financials.read",
      "trip_profitability.read",
      "expenses.read",
      "fuel.read",
      "cash_advance.read",
      "financial_review.read",
    ]),
  );
});

await check("Dashboard auto-loads four sample trips", async () => {
  await page.goto(base + "/dashboard");
  await page.getByTestId("Contribution").waitFor();
  assert.equal(
    await page.getByTestId("Contribution").innerText(),
    "₱33,750.00",
  );
  assert(
    await page
      .getByText(/SYNTHETIC VALIDATION DATA/)
      .first()
      .isVisible(),
  );
});

await check("Intelligence loads explainable sample findings", async () => {
  await page.getByRole("link", { name: "Intelligence", exact: true }).click();
  await page.locator(".reporting-findings").first().waitFor();
  const response = await page.request.get(
    base +
      "/api/v1/intelligence/exceptions?dataset=synthetic&date_from=2026-09-21&date_to=2026-09-24",
  );
  assert.equal(response.status(), 200);
  const data = await response.json();
  const loss = data.items.find((item) => item.rule_id === "NEGATIVE_CONTRIBUTION");
  const fuel = data.items.find(
    (item) => item.rule_id === "COST_CONCENTRATION:FUEL",
  );
  assert.equal(loss?.supporting_values?.contribution, "-1200.00");
  assert.equal(fuel?.supporting_values?.share_percent, "60.00");
});
const reports = [
  "executive-contribution",
  "trip-contribution",
  "customer-contribution",
  "direct-costs",
  "financial-exceptions",
  "cash-advances",
];
await check("All six reports and CSV exports are readable", async () => {
  for (const report of reports) {
    await page.goto(base + "/reports/" + report);
    await page.locator(".reporting-main-report").waitFor();
    const csv = await page.request.get(
      base +
        "/api/v1/reports/" +
        report +
        "?dataset=synthetic&date_from=2026-09-21&date_to=2026-09-24&format=csv",
    );
    assert.equal(csv.status(), 200, report);
    assert((await csv.text()).includes("SYNTHETIC VALIDATION DATA"), report);
  }
});

await check("Sample trip financial drill-down is readable", async () => {
  await page.goto(
    base +
      "/reports/trip-contribution?dataset=synthetic&date_from=2026-09-21&date_to=2026-09-24&trip_id=7abd2431-ae5c-4a27-af2c-dd5f02e04316",
  );
  await page
    .getByRole("heading", { name: "Financial performance", exact: true })
    .waitFor();
  assert(
    await page.getByText("−₱1,200.00", { exact: true }).first().isVisible(),
  );
});
await check("Settings and owner/operator controls are hidden", async () => {
  assert.equal(
    await page.getByRole("link", { name: "Settings", exact: true }).count(),
    0,
  );
  assert.equal(
    await page
      .getByRole("button", { name: /Start pickup|Dispatch|Complete trip/ })
      .count(),
    0,
  );
  await page.goto(base + "/settings/organization");
  await page.waitForURL(/\/access-denied$/);
});

await check("Mutations and administration return RBAC 403", async () => {
  const me = await (await page.request.get(base + "/api/v1/me")).json();
  const org = me.organization;
  const attempts = [
    await browserRequest("/api/v1/organizations/" + org.id, {
      method: "PATCH",
      body: JSON.stringify({
        name: org.name,
        legal_name: org.legal_name,
        timezone: org.timezone,
        currency: org.currency,
        country: org.country,
      }),
    }),
    await browserRequest("/api/v1/reports/policy", {
      method: "PATCH",
      body: JSON.stringify({
        low_margin_percent: "16.00",
        direct_cost_pressure_percent: "70.00",
        cost_concentration_percent: "50.00",
        material_change_php: "1000.00",
      }),
    }),
    await browserRequest("/api/v1/memberships"),
    await browserRequest("/api/v1/audit-logs"),
  ];
  assert(attempts.every((x) => x.status === 403));
  assert(attempts.every((x) => x.body?.error?.code !== "csrf_rejected"));
});
await check("Financial mutation endpoints return RBAC 403", async () => {
  const tripId = "7abd2431-ae5c-4a27-af2c-dd5f02e04316";
  const attempts = [
    await browserRequest("/api/v1/trips/" + tripId + "/revenue", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ revenue_type: "SURCHARGE", amount: "1.00" }),
    }),
    await browserRequest("/api/v1/trips/" + tripId + "/cash-advances", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({
        amount: "100.00",
        purpose: "Denied client demo mutation",
      }),
    }),
  ];
  assert(attempts.every((x) => x.status === 403));
  assert(attempts.every((x) => x.body?.error?.code !== "csrf_rejected"));
});

await check("Cross-tenant entity filter is rejected", async () => {
  const response = await page.request.get(
    base +
      "/api/v1/reports/trip-contribution?dataset=synthetic&date_from=2026-09-21&date_to=2026-09-24&customer_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  );
  assert.equal(response.status(), 404);
});
await check("Mobile Intelligence remains readable", async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base + "/intelligence");
  await page.locator(".reporting-findings").first().waitFor();
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 2,
    ),
  );
});

await check("No unhandled browser errors", async () => {
  assert.deepEqual(errors, []);
});

const failed = checks.filter((item) => item.status === "FAIL");
await fs.writeFile(
  path.join(root, ".runtime/batch16/client-demo-public-result.json"),
  JSON.stringify(
    {
      base,
      username: credential.email,
      password_logged: false,
      source_records_changed: false,
      checked_at: new Date().toISOString(),
      checks,
    },
    null,
    2,
  ),
);
await context.close();
await browser.close();
console.log(
  JSON.stringify({
    passed: checks.length - failed.length,
    failed: failed.length,
  }),
);
process.exitCode = failed.length ? 1 : 0;
