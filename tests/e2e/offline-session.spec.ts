import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

function verifyOriginals() {
  execFileSync(
    resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
    ["scripts/verify-design-assets.py"],
    {
      encoding: "utf8",
      timeout: 30000,
    },
  );
}
test.beforeAll(verifyOriginals);
test.setTimeout(150000);
test.afterAll(verifyOriginals);
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
async function readyOffline(page: Page, trip: Trip) {
  await page.goto(`/driver/trips/${trip.id}`);
  await expect(
    page.getByRole("heading", { name: trip.trip_number, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Delivery evidence", { exact: true }),
  ).toBeVisible();
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await expect
    .poll(() =>
      page.evaluate(
        async () =>
          !!(await (
            await caches.open("fleetpilot-driver-shell-v1")
          ).match("/driver-offline")),
      ),
    )
    .toBe(true);
  await page.reload();
  await expect
    .poll(() => page.evaluate(() => !!navigator.serviceWorker.controller))
    .toBe(true);
  await expect(
    page.getByRole("heading", { name: trip.trip_number, exact: true }),
  ).toBeVisible();
}

test("Expired session locks pending work and same driver login safely resumes it", async ({
  page,
  context,
}) => {
  const fixture = provision("offline-expired");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await readyOffline(page, trip);
  await context.setOffline(true);
  page.on("dialog", (d) => d.accept());
  await page
    .getByRole("button", { name: "Start / en route to pickup", exact: true })
    .click();
  await expect(page.getByText(/1 actions saved locally/)).toBeVisible();
  // APIRequestContext can reach the test server while page networking is offline.
  expect(
    (await page.request.post("/api/v1/auth/logout", { headers })).status(),
  ).toBe(204);
  await context.setOffline(false);
  await expect(
    page.getByText(
      "Saved work is locked. Reconnect and sign in with the same account to continue.",
      { exact: true },
    ),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Sign in to continue", exact: true })
    .click();
  await page.getByLabel("Email address").fill(fixture.driver_email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/driver$/);
  await expect(page.getByText(/Synced \u00b7 no pending actions/)).toBeVisible({
    timeout: 30000,
  });
  const events = await (
    await page.request.get(`/api/v1/driver/trips/${trip.id}/milestones`)
  ).json();
  expect(
    events.filter(
      (e: { milestone_type: string }) =>
        e.milestone_type === "EN_ROUTE_TO_PICKUP",
    ),
  ).toHaveLength(1);
});

test("Stalled driver navigation falls back to the saved shell", async ({
  page,
  context,
}) => {
  const fixture = provision("offline-stalled-navigation");
  const trip = await prepare(page, fixture, "dispatch");
  await login(page, fixture.driver_email, true);
  await readyOffline(page, trip);
  let intercepted = false;
  await context.route(`**/driver/trips/${trip.id}`, async (route) => {
    if (route.request().serviceWorker()) {
      intercepted = true;
      await delay(15000);
      await route.abort().catch(() => {});
    } else await route.continue();
  });
  await page.reload({ timeout: 20000 });
  expect(intercepted).toBe(true);
  await expect(
    page.getByRole("heading", { name: trip.trip_number, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Start / en route to pickup",
      exact: true,
    }),
  ).toBeVisible();
});
