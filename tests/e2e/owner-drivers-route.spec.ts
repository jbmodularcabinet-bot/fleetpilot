import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test("owner Drivers compatibility route shows tenant roster, not driver app", async ({ page }) => {
  const python = resolve(
    process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
  );
  const fixture = JSON.parse(
    execFileSync(python, ["scripts/api-task.py", "--test", "tests.e2e_setup", "DRIVERS"], {
      encoding: "utf8",
      timeout: 60000,
    }),
  ) as { email: string };

  await page.goto("/login");
  await page.getByLabel("Email address").fill(fixture.email);
  await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.goto("/drivers");
  await expect(page.getByRole("heading", { name: "Drivers", exact: true })).toBeVisible();
  await expect(page.getByText("No drivers yet", { exact: true })).toBeVisible();
  await expect(page.getByText("Good day, Juan.", { exact: true })).toHaveCount(0);

  await page.goto("/drivers/new");
  await page.getByLabel("Employee number *").fill("DRV-001");
  await page.getByLabel("First name *").fill("Maria");
  await page.getByLabel("Last name *").fill("Santos");
  await page.getByRole("button", { name: "Save driver", exact: true }).click();
  await expect(page).toHaveURL(/\/fleet\/drivers\/[0-9a-f-]+\?saved=1$/);

  const driverId = new URL(page.url()).pathname.split("/").at(-1)!;
  await page.goto("/drivers");
  await page.getByLabel("Search drivers").fill("Maria");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByRole("link", { name: "View Maria Santos" })).toBeVisible();

  await page.goto(`/drivers/${driverId}`);
  await expect(page.getByRole("heading", { name: "Maria Santos" })).toBeVisible();
  await expect(page.getByText("No login account linked", { exact: true })).toBeVisible();

  await page.goto("/driver");
  await expect(page).not.toHaveURL(/\/drivers(?:\/|$)/);
});
