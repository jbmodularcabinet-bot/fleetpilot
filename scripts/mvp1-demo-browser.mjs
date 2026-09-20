import fs from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";
import { fileURLToPath, pathToFileURL } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const oldRoot = "C:/Users/User/Documents/ChatGPT/FleetPilot";
const { chromium } = await import(
  pathToFileURL(path.join(oldRoot, "node_modules/playwright/index.mjs")).href
);
const args = process.argv.slice(2);
const base = args[0] ?? "http://localhost:3500";
const label = args[1] ?? "demo-local";
const authorized = JSON.parse(
  await fs.readFile(
    path.join(root, ".runtime/batch16/authorized-demo-origin.json"),
    "utf8",
  ),
);
assert(
  [authorized.origin, authorized.local_origin].includes(base),
  "Credential use is restricted to the authorized local demo origins",
);
const output = path.join(root, ".runtime/batch16", label);
await fs.mkdir(output, { recursive: true });
const env = Object.fromEntries(
  (await fs.readFile(path.join(oldRoot, ".env"), "utf8"))
    .split(/\r?\n/)
    .filter((l) => l.includes("=") && !l.trim().startsWith("#"))
    .map((l) => {
      const i = l.indexOf("=");
      return [
        l.slice(0, i).trim(),
        l
          .slice(i + 1)
          .trim()
          .replace(/^["']|["']$/g, ""),
      ];
    }),
);
assert(env.DEMO_PASSWORD, "Existing local demo credential is required");
const query = "dataset=synthetic&date_from=2026-09-21&date_to=2026-09-24";
const reports = [
  ["executive-contribution", "Executive Contribution"],
  ["trip-contribution", "Trip Contribution"],
  ["customer-contribution", "Customer Contribution"],
  ["direct-costs", "Direct Cost Analysis"],
  ["financial-exceptions", "Financial Exceptions"],
  ["cash-advances", "Cash Advance & Settlement"],
];
const results = [],
  failures = [];
let browser;
async function check(name, operation) {
  try {
    await operation();
    results.push({ name, status: "PASS" });
    console.log("PASS " + name);
  } catch (error) {
    failures.push({ name, error: error.message });
    results.push({ name, status: "FAIL", error: error.message });
    console.log("FAIL " + name + ": " + error.message);
  }
}
function golden(data) {
  assert.equal(data.summary.revenue, "74000.00");
  assert.equal(data.summary.direct_cost, "40250.00");
  assert.equal(data.summary.contribution, "33750.00");
  assert.equal(data.summary.weighted_margin_percent, "45.61");
  assert.equal(data.summary.trip_count, 4);
  assert.equal(data.summary.provisional_count, 4);
  assert.equal(data.summary.final_count, 0);
  assert.equal(data.summary.positive_count, 3);
  assert.equal(data.summary.negative_count, 1);
  assert(data.scope.synthetic);
}
try {
  browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
    acceptDownloads: true,
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await check("Actual login form and authenticated dashboard", async () => {
    await page.goto(base + "/login", { waitUntil: "domcontentloaded" });
    await page.locator('input[type="email"]').fill("carlo@example.com");
    await page.locator('input[type="password"]').fill(env.DEMO_PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL(/\/dashboard(?:\?|$)/, { timeout: 30000 });
    const me = await page.request.get(base + "/api/v1/me");
    assert.equal(me.status(), 200);
  });
  if (failures.length)
    throw new Error(
      "Authentication gate did not pass; stopped authenticated demo checks",
    );
  await check("Dashboard golden totals and synthetic period", async () => {
    await page.goto(base + "/dashboard?" + query);
    await page.getByTestId("Contribution").waitFor();
    assert.equal(
      await page.getByTestId("Contribution").innerText(),
      "₱33,750.00",
    );
    assert.equal(
      await page.getByTestId("Weighted Contribution Margin").innerText(),
      "45.61%",
    );
    assert(await page.locator(".reporting-demo-banner").isVisible());
    const response = await page.request.get(
      base + "/api/v1/intelligence/overview?" + query,
    );
    assert.equal(response.status(), 200);
    const data = await response.json();
    golden(data);
    await fs.writeFile(
      path.join(output, "golden-overview.json"),
      JSON.stringify(data, null, 2),
    );
    await page.screenshot({
      path: path.join(output, "01-dashboard-desktop.png"),
      fullPage: true,
    });
  });
  await check(
    "Intelligence loss and fuel concentration explainability",
    async () => {
      await page.goto(base + "/intelligence?" + query);
      await page.locator(".reporting-findings").first().waitFor();
      const response = await page.request.get(
        base + "/api/v1/intelligence/exceptions?" + query,
      );
      const data = await response.json();
      golden(data);
      const loss = data.items.find(
        (f) => f.rule_id === "NEGATIVE_CONTRIBUTION",
      );
      assert(loss);
      assert.equal(loss.supporting_values.contribution, "-1200.00");
      const fuel = data.items.find(
        (f) => f.rule_id === "COST_CONCENTRATION:FUEL",
      );
      assert(fuel);
      assert.equal(fuel.supporting_values.share_percent, "60.00");
      await page.screenshot({
        path: path.join(output, "02-intelligence.png"),
        fullPage: true,
      });
    },
  );
  for (const [name, title] of reports) {
    await check("Report / CSV / print: " + title, async () => {
      await page.goto(base + "/reports/" + name + "?" + query);
      await page.locator(".reporting-main-report").waitFor();
      assert(
        await page
          .getByRole("heading", { name: title, exact: true })
          .isVisible(),
      );
      const response = await page.request.get(
        base + "/api/v1/reports/" + name + "?" + query,
      );
      assert.equal(response.status(), 200);
      golden(await response.json());
      const csv = await page.request.get(
        base + "/api/v1/reports/" + name + "?" + query + "&format=csv",
      );
      assert.equal(csv.status(), 200);
      const text = await csv.text();
      assert(text.includes("SYNTHETIC VALIDATION DATA"));
      assert(text.includes("not net profit"));
      assert(text.includes("Asia/Manila"));
      await fs.writeFile(path.join(output, name + ".csv"), text);
      const print = await page.request.get(
        base + "/api/v1/reports/" + name + "?" + query + "&format=print",
      );
      assert.equal(print.status(), 200);
      assert((await print.text()).includes("Print / Save as PDF"));
      await page.screenshot({
        path: path.join(output, "report-" + name + ".png"),
        fullPage: true,
      });
    });
  }
  await check("Capture is not issuance or inferred outstanding", async () => {
    const response = await page.request.get(
      base + "/api/v1/reports/cash-advances?" + query,
    );
    const data = await response.json();
    assert.equal(data.advance_summary.captured_amount, "5000.00");
    assert.equal(data.advance_summary.issued, "0.00");
    assert.equal(data.advance_summary.outstanding, "0.00");
    assert.equal(data.advance_summary.unreconciled_capture_count, 1);
    assert.equal(
      data.items.filter((i) => i.record_kind === "CAPTURE").length,
      1,
    );
    assert.equal(
      data.items.filter((i) => i.record_kind === "ISSUANCE").length,
      0,
    );
  });
  await check("Filtered trip source review works", async () => {
    await page.goto(
      base +
        "/reports/trip-contribution?" +
        query +
        "&trip_id=7abd2431-ae5c-4a27-af2c-dd5f02e04316",
    );
    await page
      .getByRole("heading", { name: "Financial performance", exact: true })
      .waitFor();
    await page
      .getByRole("heading", { name: "Revenue history", exact: true })
      .waitFor();
    assert(
      await page.getByText("−₱1,200.00", { exact: true }).first().isVisible(),
    );
    await page.screenshot({
      path: path.join(output, "trip-source-review.png"),
      fullPage: true,
    });
  });
  await check("Business scope excludes the four synthetic trips", async () => {
    const response = await page.request.get(
      base +
        "/api/v1/reports/trip-contribution?date_from=2026-09-21&date_to=2026-09-24&dataset=business",
    );
    assert.equal(response.status(), 200);
    const data = await response.json();
    const synthetic = new Set([
      "a60a03eb-30d9-432b-b741-545a490c10a4",
      "58b13f70-5eb8-4f0e-809f-8d8fa07dff4d",
      "7abd2431-ae5c-4a27-af2c-dd5f02e04316",
      "efa687f1-94c0-426d-977e-b75fd4a239f9",
    ]);
    assert(data.items.every((t) => !synthetic.has(t.id)));
    assert.equal(data.scope.synthetic, false);
  });
  await check("Actual CSV download button", async () => {
    await page.goto(base + "/reports/trip-contribution?" + query);
    await page.locator(".reporting-main-report").waitFor();
    const downloading = page.waitForEvent("download");
    await page
      .getByRole("button", {
        name: "Export complete filtered CSV",
        exact: true,
      })
      .click();
    const download = await downloading;
    await download.saveAs(path.join(output, "button-download.csv"));
    assert(
      (
        await fs.readFile(path.join(output, "button-download.csv"), "utf8")
      ).includes("33750") ||
        (
          await fs.readFile(path.join(output, "button-download.csv"), "utf8")
        ).includes("-1200.00"),
    );
  });
  await check("Mobile dashboard and horizontal containment", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(base + "/dashboard?" + query);
    await page.getByTestId("Contribution").waitFor();
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 2,
      ),
    );
    await page.screenshot({
      path: path.join(output, "dashboard-mobile.png"),
      fullPage: true,
    });
    await page.goto(base + "/reports/trip-contribution?" + query);
    await page.locator(".reporting-main-report").waitFor();
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 2,
      ),
    );
    await page.screenshot({
      path: path.join(output, "trip-report-mobile.png"),
      fullPage: true,
    });
  });
  await check("Browser has no unhandled JavaScript errors", async () => {
    assert.deepEqual(errors, []);
  });
  await check("Anonymous report/export denied", async () => {
    const anonymous = await browser.newContext();
    const a = await anonymous.request.get(
      base + "/api/v1/reports/executive-contribution?" + query,
    );
    assert.equal(a.status(), 401);
    const e = await anonymous.request.get(
      base + "/api/v1/reports/trip-contribution?" + query + "&format=csv",
    );
    assert.equal(e.status(), 401);
    await anonymous.close();
  });
  await context.close();
} catch (error) {
  failures.push({ name: "Demo execution", error: error.message });
  console.log("DEMO EXECUTION STOP: " + error.message);
} finally {
  if (browser) await browser.close();
  const result = {
    base_url: base,
    label,
    synthetic: true,
    source_records_changed: false,
    passed: results.filter((r) => r.status === "PASS").length,
    failed: failures.length,
    checks: results,
    failures,
  };
  await fs.writeFile(
    path.join(output, "result.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(
    JSON.stringify({
      passed: result.passed,
      failed: result.failed,
      evidence: output,
    }),
  );
  process.exitCode = failures.length ? 1 : 0;
}
