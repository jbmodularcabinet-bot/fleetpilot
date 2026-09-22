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
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(base + "/login");
  await page.getByLabel("Email address").fill("carlo@example.com");
  await page.getByLabel("Password", { exact: true }).fill(env.DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL(/\/dashboard(?:\?|$)/);
  const me = await (await page.request.get(base + "/api/v1/me")).json();
  const result = { organization: me.organization.name, pages: [], checked_at: new Date().toISOString() };
  for (const target of ["/intelligence", "/reports/executive-contribution", "/reports/trip-contribution", "/reports/cash-advances"]) {
    await page.goto(base + target);
    await page.locator(".reporting-scope").waitFor();
    result.pages.push({path: target, scope: await page.locator(".reporting-scope").innerText(), demo_button: await page.getByRole("button", { name: "Demo: Sep 21–24, 2026", exact: true }).count()});
  }
  const synthetic = await page.request.get(base + "/api/v1/intelligence/overview?dataset=synthetic&date_from=2026-09-21&date_to=2026-09-24");
  const payload = await synthetic.json();
  result.retained_sample = {http_status:synthetic.status(), summary:payload.summary, scope:payload.scope};
  await fs.writeFile(path.join(output,"entry-audit.json"),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result,null,2));
} finally { await browser.close(); }
