import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { expectLockedV1 } from "./design-v1";
test.setTimeout(150000);
interface Fixture {
  email: string;
  driver_email: string;
  driver_user_id: string;
  organization_id: string;
}
interface Trip {
  id: string;
  version: number;
  trip_number: string;
  current_status: string;
}
const headers = { Origin: "http://localhost:3100" };
const actions = [
  "dispatch",
  "start_pickup",
  "arrive_pickup",
  "start_loading",
  "finish_loading",
  "depart_pickup",
  "arrive_delivery",
  "start_unloading",
  "finish_unloading",
];
function provision(label: string): Fixture {
  return JSON.parse(
    execFileSync(
      resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
      ["scripts/api-task.py", "--test", "tests.e2e_setup", label, "--driver"],
      { encoding: "utf8", timeout: 60000 },
    ),
  );
}
async function login(page: Page, email: string, driver = false) {
  await page.request.post("/api/v1/auth/logout", { headers });
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(driver ? /\/driver$/ : /\/dashboard$/, {
    timeout: 30000,
  });
}
async function post(api: APIRequestContext, path: string, data: unknown) {
  const r = await api.post(`/api/v1${path}`, { headers, data });
  expect(r.ok(), await r.text()).toBe(true);
  return r.json();
}
async function prepare(
  page: Page,
  fixture: Fixture,
  stop = "finish_unloading",
): Promise<Trip> {
  await login(page, fixture.email);
  const customer = await post(page.request, "/customers", {
    customer_code: "ACME-001",
    company_name: "ACME Logistics Client",
  });
  const vehicle = await post(page.request, "/vehicles", {
    unit_number: "TRK-001",
    plate_number: "ABC-1234",
    vehicle_type: "Wing van",
  });
  const driver = await post(page.request, "/drivers", {
    employee_number: "DRV-001",
    first_name: "Juan",
    last_name: "Dela Cruz",
    user_id: fixture.driver_user_id,
  });
  let trip = await post(page.request, "/trips", {
    customer_id: customer.id,
    vehicle_id: vehicle.id,
    driver_id: driver.id,
    pickup_name: "Warehouse A",
    pickup_address: "100 Test Road, Manila",
    delivery_name: "Customer Site B",
    delivery_address: "200 Test Road, Laguna",
    scheduled_pickup_at: "2030-02-10T08:00:00+08:00",
    scheduled_delivery_at: "2030-02-10T16:00:00+08:00",
  });
  for (const action of actions) {
    trip = await post(page.request, `/trips/${trip.id}/transition`, {
      expected_version: trip.version,
      action,
    });
    if (action === stop) break;
  }
  return trip;
}

test("closed-trip adjustment and reversal golden preserve history and locked design", async ({
  page,
}) => {
  const fixture = provision("adjustments-golden");
  let trip = await prepare(page, fixture);
  const ids: string[] = [];
  for (const fields of [
    { category: "FUEL", liters: "50", price_per_liter: "60" },
    { category: "TOLL", amount: "300.00" },
    { category: "PARKING", amount: "100.00" },
  ]) {
    const r = await page.request.post(`/api/v1/trips/${trip.id}/expenses`, {
      headers: { ...headers, "Idempotency-Key": randomUUID() },
      data: {
        ...fields,
        expected_version: trip.version,
        occurred_at: new Date().toISOString(),
      },
    });
    expect(r.ok(), await r.text()).toBe(true);
    const result = (await r.json()).result;
    ids.push(result.expense.id);
    trip.version = result.trip_version;
  }
  const attempt = await post(
    page.request,
    `/trips/${trip.id}/delivery-attempts`,
    { expected_version: trip.version },
  );
  const image = await page.request.post(
    `/api/v1/delivery-attempts/${attempt.attempt.id}/evidence?expected_version=${attempt.trip_version}&evidence_type=DELIVERY_PHOTO&filename=delivery.png`,
    {
      headers: { ...headers, "Content-Type": "image/png" },
      data: readFileSync("tests/fixtures/delivery.png"),
    },
  );
  expect(image.ok()).toBe(true);
  const delivered = await post(
    page.request,
    `/delivery-attempts/${attempt.attempt.id}/pod`,
    {
      expected_version: (await image.json()).trip_version,
      recipient_name: "Maria Santos",
      driver_confirmed: true,
    },
  );
  const reviewed = await post(page.request, `/pod/${delivered.pod.id}/review`, {
    expected_version: delivered.trip.version,
  });
  trip = await post(page.request, `/trips/${trip.id}/complete`, {
    expected_version: reviewed.trip_version,
    closeout_reviewed: true,
  });
  await page.goto(`/trips/${trip.id}`);
  await expectLockedV1(page, false);
  const section = page.getByRole("region", {
    name: "Administrative adjustments",
  });
  await expect(
    section.getByText("No administrative adjustments."),
  ).toBeVisible();
  await section
    .getByRole("button", { name: "Create adjustment", exact: true })
    .click();
  await section.getByLabel("Expense record").selectOption(ids[1]);
  await section.getByLabel("Corrected value").fill("350.00");
  await section
    .getByLabel("Adjustment reason")
    .fill("Receipt verified after trip close.");
  await expect(
    section.getByRole("button", { name: "Apply adjustment" }),
  ).toBeDisabled();
  await section.getByLabel(/This will not overwrite/).check();
  await section.getByRole("button", { name: "Apply adjustment" }).click();
  await expect(
    section.getByText("Adjustment applied. Original record is unchanged."),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.locator(".expense-panel").getByText(/Total trip expenses: ₱3,450.00/),
  ).toBeVisible();
  await expect(section.getByText(/Adjustment 50.00 PHP/)).toBeVisible();
  expect(
    (await (await page.request.get(`/api/v1/expenses/${ids[1]}`)).json())
      .current.amount,
  ).toBe("300.00");
  await page.setViewportSize({ width: 390, height: 844 });
  await expectLockedV1(page, false);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await section.screenshot({ path: "test-results/batch9-adjustment-section.png" });
  await page.screenshot({
    path: "test-results/batch9-adjustment-mobile.png",
    fullPage: true,
  });
  await section
    .getByRole("button", { name: "Reverse adjustment", exact: true })
    .click();
  await section
    .getByLabel("Adjustment reason")
    .fill("Adjustment entered in error.");
  await section.getByLabel(/This will not overwrite/).check();
  await section.getByRole("button", { name: "Confirm reversal" }).click();
  await expect(
    section.getByText("Adjustment reversed. History is preserved."),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.locator(".expense-panel").getByText(/Total trip expenses: ₱3,400.00/),
  ).toBeVisible();
  await expect(section.getByText("Adjustment entered in error.")).toBeVisible();
  const unchanged = await (
    await page.request.get(`/api/v1/trips/${trip.id}`)
  ).json();
  expect(unchanged.current_status).toBe("COMPLETED");
  expect(unchanged.version).toBe(trip.version);
  await login(page, fixture.driver_email, true);
  await page.goto(`/driver/trips/${trip.id}`);
  await expect(section).toHaveCount(0);
  const denied = await page.request.post(
    `/api/v1/trips/${trip.id}/adjustments`,
    {
      headers: { ...headers, "Idempotency-Key": randomUUID() },
      data: {
        target_id: ids[1],
        expected_sequence: 2,
        adjustment_type: "AMOUNT_CORRECTION",
        new_value: "500.00",
        reason: "Driver must not change closed costs",
      },
    },
  );
  expect(denied.status()).toBe(403);
});
