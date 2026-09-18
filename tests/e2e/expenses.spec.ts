import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { execFileSync } from "node:child_process";
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
      resolve(".venv/Scripts/python.exe"),
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

async function add(
  page: Page,
  category: string,
  amount?: string,
  receipt = false,
) {
  const panel = page.locator(".expense-panel");
  await panel.getByRole("button", { name: "Add expense", exact: true }).click();
  await panel.getByLabel("Expense category").selectOption(category);
  if (category === "FUEL") {
    await panel.getByLabel("Liters", { exact: true }).fill("52.35");
    await panel
      .getByLabel("Price per liter (PHP)", { exact: true })
      .fill("61.75");
    await panel.getByLabel("Odometer (km, optional)").fill("12500");
    await expect(panel.getByText(/Estimated total: ₱3,232.61/)).toBeVisible();
  } else await panel.getByLabel("Amount (PHP)", { exact: true }).fill(amount!);
  if (receipt)
    await panel
      .getByLabel(/Receipts \(optional/)
      .setInputFiles("tests/fixtures/delivery.png");
  await panel
    .getByRole("button", { name: "Save expense", exact: true })
    .click();
  await expect(
    panel.getByRole("button", { name: "Add expense", exact: true }),
  ).toBeVisible();
}
test("online expense golden, receipt, owner review, correction, void and fuel history", async ({
  page,
}) => {
  const fixture = provision("expenses-online");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await page.goto(`/driver/trips/${trip.id}`);
  await expect(page.locator(".expense-panel")).toBeVisible();
  await expectLockedV1(page, true);
  for (const [category, amount] of [
    ["FUEL", ""],
    ["TOLL", "350.00"],
    ["PARKING", "100.00"],
    ["DRIVER_ALLOWANCE", "500.00"],
  ]) {
    await add(page, category, amount, category === "FUEL");
    await expect(page.getByText(/Synced · no pending actions/)).toBeVisible({
      timeout: 30000,
    });
  }
  await expect(
    page.locator(".expense-panel").getByText(/Total trip expenses: ₱4,182.61/),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.locator(".expense-panel").getByText(/Total trip expenses: ₱4,182.61/),
  ).toBeVisible();
  await login(page, fixture.email);
  await page.goto(`/trips/${trip.id}`);
  await expectLockedV1(page, false);
  const panel = page.locator(".expense-panel");
  await panel
    .getByRole("button", { name: "View expense", exact: true })
    .last()
    .click();
  await expect(panel.getByRole("img", { name: "delivery.png" })).toBeVisible();
  await panel
    .getByRole("button", { name: "Review expense", exact: true })
    .click();
  await panel.getByLabel("Review notes").fill("Receipt verified");
  await panel
    .getByRole("button", { name: "Confirm review", exact: true })
    .click();
  await expect(panel.getByText(/Reviewed: ₱3,232.61/)).toBeVisible();
  for (let i = 0; i < 3; i++) {
    await panel
      .getByRole("button", { name: "View expense", exact: true })
      .nth(i)
      .click();
    await panel
      .getByRole("button", { name: "Review expense", exact: true })
      .click();
    await panel
      .getByRole("button", { name: "Confirm review", exact: true })
      .click();
    await expect(
      panel.getByRole("button", { name: "Confirm review", exact: true }),
    ).toHaveCount(0);
  }
  await expect(panel.getByText(/Reviewed: ₱4,182.61/)).toBeVisible();

  await panel
    .getByRole("button", { name: "View expense", exact: true })
    .nth(2)
    .click();
  await panel
    .getByRole("button", { name: "Correct expense", exact: true })
    .click();
  await panel.getByLabel("Amount (PHP)", { exact: true }).fill("300.00");
  await panel.getByLabel("Correction reason").fill("Receipt amount corrected");
  await panel
    .getByRole("button", { name: "Save correction", exact: true })
    .click();
  await expect(panel.getByText(/Total trip expenses: ₱4,132.61/)).toBeVisible();
  await panel
    .getByRole("button", { name: "View expense", exact: true })
    .nth(2)
    .click();
  await expect(panel.getByText(/Revision 1: Toll · ₱350.00/)).toBeVisible();
  await expect(panel.getByText(/Revision 2: Toll · ₱300.00/)).toBeVisible();
  await panel
    .getByRole("button", { name: "Void expense", exact: true })
    .click();
  await panel.getByLabel(/Void reason/).fill("Invalid operational entry");
  await panel
    .getByRole("button", { name: "Confirm void", exact: true })
    .click();
  await expect(panel.getByText(/Total trip expenses: ₱3,832.61/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/batch8-owner.png",
    fullPage: true,
  });
  const actual = await (
    await page.request.get(`/api/v1/trips/${trip.id}`)
  ).json();
  await page.goto(`/fleet/vehicles/${actual.vehicle_id}`);
  await expect(
    page.getByRole("heading", { name: "Vehicle fuel history" }),
  ).toBeVisible();
  await expect(page.getByText(/52.350 L/)).toBeVisible();
});
test("sequential offline expenses from an already-open second tab retain distinct versions", async ({
  page,
  context,
}) => {
  const fixture = provision("expenses-stale-tab");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await page.goto(`/driver/trips/${trip.id}`);
  const second = await context.newPage();
  await second.goto(`/driver/trips/${trip.id}`);
  for (const tab of [page, second]) {
    await expect(
      tab.locator(".expense-panel").getByText("No expenses recorded yet."),
    ).toBeVisible();
    await tab.evaluate(async () => {
      await navigator.serviceWorker.ready;
    });
  }
  await context.setOffline(true);
  await add(page, "TOLL", "300.00", true);
  await add(second, "PARKING", "100.00");
  const versions = await second.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("fleetpilot-driver-v1", 2);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const rows = await new Promise<
      { sequence: number; expected_version: number }[]
    >((resolve, reject) => {
      const request = db.transaction("actions").objectStore("actions").getAll();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    db.close();
    return rows
      .sort((a, b) => a.sequence - b.sequence)
      .map((row) => row.expected_version);
  });
  expect(versions).toEqual([trip.version, trip.version + 1, trip.version + 2]);
  await context.setOffline(false);
  await expect(second.getByText(/Synced · no pending actions/)).toBeVisible({
    timeout: 30000,
  });
  const result = await (
    await second.request.get(`/api/v1/trips/${trip.id}/expenses`)
  ).json();
  expect(result.total).toBe(2);
  expect(result.submitted_total).toBe("400.00");
});

test("offline expense and receipt survive page restart and lost reply without duplicate cost", async ({
  page,
  context,
}) => {
  const fixture = provision("expenses-offline");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/driver/trips/${trip.id}`);
  await expect(
    page.locator(".expense-panel").getByText("No expenses recorded yet."),
  ).toBeVisible();
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await context.setOffline(true);
  await add(page, "FUEL", "", true);
  await add(page, "TOLL", "350.00", true);
  await add(page, "PARKING", "100.00");
  await add(page, "DRIVER_ALLOWANCE", "500.00");
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Saved locally. The status badge" }),
  ).toBeVisible();
  await page.close();
  const reopened = await context.newPage();
  await reopened.goto(`/driver/trips/${trip.id}`);
  await expect(reopened.locator(".expense-panel")).toBeVisible();
  await expectLockedV1(reopened, true);
  await reopened.getByText("Saved work (6)", { exact: true }).click();
  await expect(
    reopened.getByRole("link", { name: "FUEL · ₱3,232.61" }),
  ).toBeVisible();
  await expect(
    reopened.getByRole("link", { name: "Receipt: delivery.png" }),
  ).toHaveCount(2);

  let dropped = false;
  let droppedKey = "";
  let replayed = false;
  await context.route("**/api/v1/driver/sync/*/expense", async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    if (!dropped) {
      dropped = true;
      droppedKey = route.request().headers()["idempotency-key"];
      await route.abort("failed");
    } else {
      if (route.request().headers()["idempotency-key"] === droppedKey) {
        expect((await response.json()).outcome).toBe("ALREADY_APPLIED");
        replayed = true;
      }
      await route.fulfill({ response });
    }
  });
  await context.setOffline(false);
  await expect.poll(() => dropped, { timeout: 30000 }).toBe(true);
  await expect(reopened.getByText(/Synced · no pending actions/)).toBeVisible({
    timeout: 60000,
  });
  expect(replayed).toBe(true);
  await expect(
    reopened
      .locator(".expense-panel")
      .getByText(/Total trip expenses: ₱4,182.61/),
  ).toBeVisible();
  const costs = await (
    await reopened.request.get(`/api/v1/trips/${trip.id}/expenses`)
  ).json();
  expect(costs.total).toBe(4);
  const fuel = costs.items.find(
    (r: { category: string }) => r.category === "FUEL",
  );
  const detail = await (
    await reopened.request.get(`/api/v1/expenses/${fuel.id}`)
  ).json();
  expect(detail.evidence).toHaveLength(1);
  const toll = costs.items.find(
    (r: { category: string }) => r.category === "TOLL",
  );
  expect(
    (await (await reopened.request.get(`/api/v1/expenses/${toll.id}`)).json())
      .evidence,
  ).toHaveLength(1);
  await reopened.screenshot({
    path: "test-results/batch8-driver-offline.png",
    fullPage: true,
  });
});
