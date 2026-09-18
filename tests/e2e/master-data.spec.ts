import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

function provision(label: string): { email: string; organization_id: string } {
  const python = resolve(
    process.platform === "win32"
      ? ".venv/Scripts/python.exe"
      : ".venv/bin/python",
  );
  return JSON.parse(
    execFileSync(
      python,
      ["scripts/api-task.py", "--test", "tests.e2e_setup", label],
      { encoding: "utf8", timeout: 60000 },
    ),
  );
}
async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}
async function save(page: Page, domain: string) {
  await page
    .getByRole("button", { name: `Save ${domain}`, exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Record saved successfully" }),
  ).toBeVisible();
  return new URL(page.url()).pathname.split("/").at(-1)!;
}
test("Batch 3 golden workflow: persisted owner CRUD, assignment history and tenant attacks", async ({
  page,
}) => {
  test.setTimeout(180000);
  const orgA = provision("A");
  await login(page, orgA.email);
  await page.getByRole("link", { name: "Customers", exact: true }).click();
  await expect(
    page.getByText("No customers yet", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Add customer", exact: true }).click();
  await page
    .getByRole("button", { name: "Save customer", exact: true })
    .click();
  await expect(page).toHaveURL(/\/customers\/new$/);
  expect(
    await page
      .getByLabel("Customer code *", { exact: true })
      .evaluate((input: HTMLInputElement) => input.validity.valueMissing),
  ).toBe(true);
  await page.getByLabel("Customer code *", { exact: true }).fill("ACME-001");
  await page
    .getByLabel("Company name *", { exact: true })
    .fill("ACME Logistics Client");
  const customer = await save(page, "customer");
  await page.getByRole("link", { name: "Edit customer", exact: true }).click();
  await page.getByLabel("Contact person", { exact: true }).fill("Ana Reyes");
  await save(page, "customer");
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Deactivate", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Record deactivated" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reactivate", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Record reactivated" }),
  ).toBeVisible();
  await page.goto("/fleet/vehicles/new");
  await page.getByLabel("Unit number *", { exact: true }).fill("TRK-001");
  await page.getByLabel("Plate number *", { exact: true }).fill("ABC-1234");
  await page.getByLabel("Vehicle type *", { exact: true }).fill("Wing van");
  const vehicle = await save(page, "vehicle");
  await page.goto("/fleet/drivers/new");
  await page.getByLabel("Employee number *", { exact: true }).fill("DRV-001");
  await page.getByLabel("First name *", { exact: true }).fill("Juan");
  await page.getByLabel("Last name *", { exact: true }).fill("Dela Cruz");
  await page.getByLabel("License expiry", { exact: true }).fill("2028-01-31");
  const driver = await save(page, "driver");
  await expect(
    page.getByText("No login account linked", { exact: true }),
  ).toBeVisible();
  await page.goto(`/fleet/vehicles/${vehicle}`);
  await page
    .getByRole("combobox", { name: "Choose driver", exact: true })
    .selectOption(driver);
  await page
    .getByRole("button", { name: "Assign driver", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Juan Dela Cruz", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("link", { name: "Juan Dela Cruz", exact: true }),
  ).toBeVisible();
  await page.goto("/fleet/vehicles");
  await page.getByLabel("Search vehicles", { exact: true }).fill("TRK-001");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("1–1 of 1", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "TRK-001", exact: true }).click();
  await page.getByRole("link", { name: "Juan Dela Cruz", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "TRK-001", exact: true }),
  ).toBeVisible();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/batch3-driver-detail-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "Unassign", exact: true }).click();
  await expect(
    page.getByText("No current assignment.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Juan Dela Cruz · TRK-001", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("ENDED", { exact: true })).toBeVisible();
  const assignments = await (
    await page.request.get(
      `/api/v1/vehicle-driver-assignments?driver_id=${driver}`,
    )
  ).json();
  const assignment = assignments.items[0].id;
  expect(assignments.items[0].is_current).toBe(false);
  for (const [domain, singular, identifier] of [
    ["vehicles", "vehicle", vehicle],
    ["drivers", "driver", driver],
  ] as const) {
    await page.goto(`/fleet/${domain}/${identifier}/edit`);
    await page.getByLabel("Notes", { exact: true }).fill("Verified owner edit");
    await save(page, singular);
    await page.getByRole("button", { name: "Deactivate", exact: true }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "Record deactivated" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Reactivate", exact: true }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "Record reactivated" }),
    ).toBeVisible();
  }
  const events = await (
    await page.request.get("/api/v1/audit-logs?limit=100")
  ).json();
  expect(events.map((event: { action: string }) => event.action)).toEqual(
    expect.arrayContaining([
      "customer.created",
      "customer.updated",
      "customer.deactivated",
      "customer.reactivated",
      "vehicle.created",
      "driver.created",
      "driver.assigned_to_vehicle",
      "driver.unassigned_from_vehicle",
    ]),
  );
  const orgB = provision("B");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await login(page, orgB.email);
  const origin = { Origin: "http://localhost:3100" };
  for (const [domain, id, body] of [
    [
      "customers",
      customer,
      { customer_code: "ACME-001", company_name: "Attack" },
    ],
    [
      "vehicles",
      vehicle,
      { unit_number: "TRK-001", plate_number: "ABC-1234", vehicle_type: "Van" },
    ],
    [
      "drivers",
      driver,
      {
        employee_number: "DRV-001",
        first_name: "Attack",
        last_name: "Attempt",
      },
    ],
  ] as const) {
    expect((await page.request.get(`/api/v1/${domain}/${id}`)).status()).toBe(
      404,
    );
    for (const search of ["", "TRK-001", "Juan", "ACME"]) {
      const result = await (
        await page.request.get(`/api/v1/${domain}?search=${search}`)
      ).json();
      expect(result.total).toBe(0);
      expect(result.items).toEqual([]);
    }
    expect(
      (
        await page.request.patch(`/api/v1/${domain}/${id}`, {
          headers: origin,
          data: body,
        })
      ).status(),
    ).toBe(404);
    expect(
      (
        await page.request.post(`/api/v1/${domain}/${id}/deactivate`, {
          headers: origin,
        })
      ).status(),
    ).toBe(404);
  }
  expect(
    (
      await page.request.get(`/api/v1/vehicle-driver-assignments/${assignment}`)
    ).status(),
  ).toBe(404);
  expect(
    (
      await page.request.post("/api/v1/vehicle-driver-assignments", {
        headers: origin,
        data: { vehicle_id: vehicle, driver_id: driver },
      })
    ).status(),
  ).toBe(404);
  expect(
    (
      await page.request.post(
        `/api/v1/vehicle-driver-assignments/${assignment}/unassign`,
        { headers: origin },
      )
    ).status(),
  ).toBe(404);
  await page.goto(`/fleet/vehicles/${vehicle}`);
  await expect(
    page.getByRole("alert").filter({ hasText: "Record not found" }),
  ).toBeVisible();
  await expect(page.getByText("Juan Dela Cruz", { exact: true })).toHaveCount(
    0,
  );
});

test("master list error recovery and mobile form", async ({ page }) => {
  const org = provision("UI");
  await login(page, org.email);
  await page.route("**/api/v1/customers?**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { message: "Temporarily unavailable" } }),
    }),
  );
  await page.goto("/customers");
  await expect(
    page.getByRole("alert").filter({ hasText: "Temporarily unavailable" }),
  ).toContainText("Temporarily unavailable");
  await page.unroute("**/api/v1/customers?**");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByText("No customers yet", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 360, height: 900 });
  await page.goto("/fleet/vehicles/new");
  await expect(
    page.getByRole("heading", { name: "Add vehicle", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/batch3-vehicle-form-360.png",
    fullPage: true,
  });
});
