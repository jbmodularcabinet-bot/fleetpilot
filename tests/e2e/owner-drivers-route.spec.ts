import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test("owner Drivers compatibility route shows tenant roster, not driver app", async ({ page }) => {
  test.setTimeout(180000);
  const python = resolve(
    process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
  );
  const fixture = JSON.parse(
    execFileSync(python, ["scripts/api-task.py", "--test", "tests.e2e_setup", "DRIVERS", "--driver"], {
      encoding: "utf8",
      timeout: 60000,
    }),
  ) as { email: string; driver_email: string };

  await page.goto("/login");
  await page.getByLabel("Email address").fill(fixture.email);
  await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("navigation", { name: "Main navigation", exact: true })
    .getByRole("link", { name: "Drivers", exact: true }).click();
  await expect(page).toHaveURL(/\/fleet\/drivers$/);
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


  // A second record catches accidental hardcoded detail/profile fallbacks.
  await page.goto("/drivers/new");
  await page.getByLabel("Employee number *").fill("DRV-002");
  await page.getByLabel("First name *").fill("Pedro");
  await page.getByLabel("Last name *").fill("Reyes");
  await page.getByRole("button", { name: "Save driver", exact: true }).click();
  await expect(page).toHaveURL(/\/fleet\/drivers\/[0-9a-f-]+\?saved=1$/);
  const secondId = new URL(page.url()).pathname.split("/").at(-1)!;
  expect(secondId).not.toBe(driverId);
  for (const [id, firstName, employee] of [
    [driverId, "Maria", "DRV-001"],
    [secondId, "Pedro", "DRV-002"],
  ]) {
    const response = await page.request.get(`/api/v1/drivers/${id}`);
    expect(response.status()).toBe(200);
    expect(await response.json()).toMatchObject({
      id, first_name: firstName, employee_number: employee,
    });
  }

  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/drivers");
    await expect(page.getByRole("heading", { name: "Drivers", exact: true })).toBeVisible();
    await expect(page.locator(".desktop-app")).toBeVisible();
    await expect(page.locator(".driver-app")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "View Maria Santos", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "View Pedro Reyes", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/owner-drivers-${width}.png`, fullPage: true });
    for (const [id, name, employee] of [
      [driverId, "Maria Santos", "DRV-001"],
      [secondId, "Pedro Reyes", "DRV-002"],
    ]) {
      await page.goto(`/drivers/${id}`);
      await page.reload();
      await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
      await expect(page.getByText(employee, { exact: true }).first()).toBeVisible();
      await expect(page.locator(".driver-app")).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `test-results/owner-driver-${employee}-${width}.png`, fullPage: true });
    }
  }

  await page.goto("/drivers");
  await page.getByLabel("Search drivers").fill("no-such-synthetic-driver");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("No matching records", { exact: true })).toBeVisible();
  await page.getByLabel("Search drivers").fill("");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("combobox", { name: "Status", exact: true }).selectOption("INACTIVE");
  await expect(page.getByText("No matching records", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Status", exact: true }).selectOption("ACTIVE");
  await expect(page.getByRole("link", { name: "View Maria Santos", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "View Pedro Reyes", exact: true })).toBeVisible();

  await page.goto("/drivers/not-a-valid-id");
  await expect(page.getByRole("heading", { name: "This page is not available.", exact: true })).toBeVisible();
  await expect(page.locator(".driver-app")).toHaveCount(0);
  await page.goto("/drivers/00000000-0000-0000-0000-000000000000");
  await expect(page.getByRole("alert").filter({ hasText: "Record not found" })).toBeVisible();
  expect(errors).toEqual([]);

  // Authenticate the actual DRIVER role in a separate, clean session.
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email address").fill(fixture.driver_email);
  await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/driver$/);
  await expect(page.locator(".driver-app")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Juan.", exact: true })).toBeVisible();
  await expect(page.locator(".desktop-app")).toHaveCount(0);
  await expect(page.getByText("No assigned trips", { exact: true })).toBeVisible();
  expect((await page.request.get("/api/v1/drivers")).status()).toBe(403);
  expect((await page.request.get(`/api/v1/drivers/${driverId}`)).status()).toBe(403);
  await page.goto("/drivers");
  await expect(page).toHaveURL(/\/driver$/);
  await expect(page.locator(".desktop-app")).toHaveCount(0);
  await page.goto(`/drivers/${driverId}`);
  await expect(page).toHaveURL(/\/driver$/);
  await expect(page.getByRole("navigation", { name: "Driver navigation", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/driver-role-preserved-320.png", fullPage: true });

  await page.goto("/driver/profile");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/drivers");
  await expect(page).toHaveURL(/\/login$/);
  expect((await page.request.get("/api/v1/drivers")).status()).toBe(401);

  // Another organization's owner cannot read either record or its history.
  const other = JSON.parse(execFileSync(python, [
    "scripts/api-task.py", "--test", "tests.e2e_setup", "DRIVERS-OTHER",
  ], { encoding: "utf8", timeout: 60000 })) as { email: string };
  await page.goto("/login");
  await page.getByLabel("Email address").fill(other.email);
  await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  for (const id of [driverId, secondId]) {
    expect((await page.request.get(`/api/v1/drivers/${id}`)).status()).toBe(404);
    expect((await page.request.get(`/api/v1/vehicle-driver-assignments?driver_id=${id}`)).status()).toBe(404);
  }
  await page.goto("/drivers");
  await expect(page.getByText("No drivers yet", { exact: true })).toBeVisible();
  await page.goto(`/drivers/${driverId}`);
  await expect(page.getByRole("alert").filter({ hasText: "Record not found" })).toBeVisible();
});
