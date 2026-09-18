import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const env = Object.fromEntries(
  readFileSync(".env", "utf8").split(/\r?\n/).filter(Boolean).map((line) => [line.slice(0, line.indexOf("=")), line.slice(line.indexOf("=") + 1)]),
);
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const errors = [];
page.on("console", (msg) => { if (msg.type() === "error") errors.push(`console: ${msg.text()}`); });
page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
await page.getByLabel("Email address").fill("carlo@example.com");
await page.getByLabel("Password").fill(env.DEMO_PASSWORD);
await Promise.all([page.waitForURL(/dashboard|\/$/, { timeout: 15000 }), page.getByRole("button", { name: "Sign in" }).click()]);
await page.goto("http://localhost:3000/dashboard", { waitUntil: "domcontentloaded" });
await page.locator("h1", { hasText: "Owner Dashboard" }).waitFor({ state: "visible", timeout: 15000 });
await page.waitForTimeout(2000);
console.log("loading visible:", await page.getByText("Loading your workspace…").isVisible().catch(() => false));
console.log("errors:", errors);
console.log("body excerpt:", (await page.locator("body").innerText()).slice(0, 1200));
await page.screenshot({ path: "test-results/dashboard-authenticated.png", fullPage: true });
await browser.close();