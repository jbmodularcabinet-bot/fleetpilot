import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expectLockedV1 } from "./design-v1";

test("legacy completed expenses are accepted without rewriting submissions and survive reload", async ({ page }) => {
  test.setTimeout(180000);
  const fixture = JSON.parse(execFileSync(
    resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
    ["scripts/api-task.py", "--test", "tests.e2e_governance", "--legacy"],
    { encoding: "utf8", timeout: 60000 },
  ));
  await page.goto("/login");
  await page.getByLabel("Email address").fill(fixture.email);
  await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/dashboard/);
  await page.goto(`/trips/${fixture.trips[0].trip.id}`);
  const panel = page.locator(".governance-panel");
  const accept = panel.getByRole("button", { name: "Accept legacy expense", exact: true });
  await expect(accept).toHaveCount(2);
  await accept.first().click();
  await expect(accept).toHaveCount(1);
  await accept.click();
  await expect(accept).toHaveCount(0);
  await panel.getByLabel("I have checked revenue, costs, adjustments and advances, and all known financial records have synchronized.").check();
  await panel.getByRole("button", { name: "Approve financial review", exact: true }).click();
  await expect(page.locator(".financial-panel").getByText("FINAL", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator(".financial-panel").getByText("FINAL", { exact: true })).toBeVisible();
  for (const id of fixture.trips[0].expenses) {
    const original = await page.request.get(`/api/v1/expenses/${id}`);
    expect(original.status()).toBe(200);
    expect((await original.json()).status).toBe("SUBMITTED");
  }
  await expectLockedV1(page, false);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
