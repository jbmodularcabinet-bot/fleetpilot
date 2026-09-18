import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
interface Fixture {
  email: string;
  organization_id: string;
  driver_email: string;
  driver_user_id: string;
}
interface Trip {
  id: string;
  version: number;
  trip_number: string;
  current_status: string;
  next_action: string | null;
  [key: string]: unknown;
}
const headers = { Origin: "http://localhost:3100" };
const labels = [
  "Dispatch trip",
  "Start / en route to pickup",
  "Arrived at pickup",
  "Start loading",
  "Loading complete",
  "Depart pickup",
  "Arrived at delivery",
  "Start unloading",
  "Unloading complete",
  "Confirm delivery",
];
const milestones = [
  "TRIP_CREATED",
  "SCHEDULED",
  "DISPATCHED",
  "EN_ROUTE_TO_PICKUP",
  "ARRIVED_PICKUP",
  "LOADING_STARTED",
  "LOADING_COMPLETED",
  "DEPARTED_PICKUP",
  "EN_ROUTE_TO_DELIVERY",
  "ARRIVED_DELIVERY",
  "UNLOADING_STARTED",
  "UNLOADING_COMPLETED",
  "DELIVERED",
  "COMPLETED",
];
function provision(label: string): Fixture {
  return JSON.parse(
    execFileSync(
      resolve(
        process.platform === "win32"
          ? ".venv/Scripts/python.exe"
          : ".venv/bin/python",
      ),
      ["scripts/api-task.py", "--test", "tests.e2e_setup", label, "--driver"],
      { encoding: "utf8", timeout: 60000 },
    ),
  );
}
async function login(page: Page, email: string, driver = false) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(driver ? /\/driver$/ : /\/dashboard$/);
}
async function logout(page: Page) {
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
}
async function post(api: APIRequestContext, path: string, data: unknown) {
  const response = await api.post(`/api/v1${path}`, { headers, data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}
async function fleet(page: Page, fixture: Fixture) {
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
  return {
    customer: customer.id as string,
    vehicle: vehicle.id as string,
    driver: driver.id as string,
  };
}
function tripBody(customer: string) {
  return {
    customer_id: customer,
    pickup_name: "Warehouse A",
    pickup_address: "100 Test Road, Manila",
    delivery_name: "Customer Site B",
    delivery_address: "200 Test Road, Laguna",
    scheduled_pickup_at: "2030-01-10T08:00:00+08:00",
    scheduled_delivery_at: "2030-01-10T16:00:00+08:00",
    special_instructions: "Proceed to Gate 4",
    dispatcher_notes: "Private operator note",
  };
}
async function uiAction(page: Page, label: string, next: string) {
  if (label === "Confirm delivery") {
    await page
      .getByLabel("Recipient name", { exact: true })
      .fill("Maria Santos");
    await page
      .getByLabel("Delivery photos (at least one required)")
      .setInputFiles("tests/fixtures/delivery.png");
    await page
      .getByRole("checkbox", {
        name: /confirm.*cargo was delivered|assigned driver confirmed delivery/i,
      })
      .check();
    await page
      .getByRole("button", { name: "Submit proof of delivery", exact: true })
      .click();
  } else await page.getByRole("button", { name: label, exact: true }).click();
  if (next)
    await expect(
      page.getByRole("button", { name: next, exact: true }),
    ).toBeVisible();
  else
    await expect(
      page.getByText("Delivery confirmed. Awaiting operator closeout.", {
        exact: true,
      }),
    ).toBeVisible();
}

test("Batch 4 owner golden workflow, immutable closeout and cross-tenant attacks", async ({
  page,
}) => {
  test.setTimeout(180000);
  const a = provision("Trip-A");
  await login(page, a.email);
  const refs = await fleet(page, a);
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("link", { name: "Dispatch Board", exact: true }).click();
  await expect(
    page.getByText("No trips in this view", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Create trip", exact: true }).click();
  await page.getByRole("button", { name: "Save trip", exact: true }).click();
  await expect(page).toHaveURL(/\/trips\/new$/);
  await page
    .getByRole("combobox", { name: "Customer", exact: true })
    .selectOption(refs.customer);
  for (const [label, value] of [
    ["Pickup name *", "Warehouse A"],
    ["Pickup address *", "100 Test Road, Manila"],
    ["Delivery name *", "Customer Site B"],
    ["Delivery address *", "200 Test Road, Laguna"],
    ["Scheduled pickup *", "2030-01-10T08:00"],
    ["Scheduled delivery", "2030-01-10T16:00"],
    ["Special instructions", "Proceed to Gate 4"],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  await page.getByRole("button", { name: "Save trip", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Trip saved successfully" }),
  ).toBeVisible();
  const id = new URL(page.url()).pathname.split("/").at(-1)!;
  await page
    .getByRole("combobox", { name: "Trip vehicle", exact: true })
    .selectOption(refs.vehicle);
  await page
    .getByRole("combobox", { name: "Trip driver", exact: true })
    .selectOption(refs.driver);
  await page.getByRole("button", { name: "Assign trip", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Dispatch trip", exact: true }),
  ).toBeVisible();
  const scheduled: Trip = await (
    await page.request.get(`/api/v1/trips/${id}`)
  ).json();
  await page.goto("/dispatch");
  await page.getByRole("button", { name: "Upcoming", exact: true }).click();
  await page
    .getByLabel("Search trips", { exact: true })
    .fill(scheduled.trip_number);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("1–1 of 1", { exact: true })).toBeVisible();
  await page
    .getByRole("link", { name: scheduled.trip_number, exact: true })
    .click();
  for (let index = 0; index < labels.length; index++)
    await uiAction(page, labels[index], labels[index + 1] ?? "");
  await page.getByRole("button", { name: "Review POD", exact: true }).click();
  await expect(page.getByText(/POD Reviewed/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Complete trip", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("checkbox", {
      name: "I reviewed the required trip details and milestone history.",
    })
    .check();
  await page
    .getByRole("button", { name: "Complete trip", exact: true })
    .click();
  await expect(
    page.getByText("Trip completed. Operational details are read-only.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("Trip completed. Operational details are read-only.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("ACME Logistics Client", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("TRK-001 · Juan Dela Cruz", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Edit trip", exact: true }),
  ).toHaveCount(0);
  const completed: Trip = await (
    await page.request.get(`/api/v1/trips/${id}`)
  ).json();
  const history = await (
    await page.request.get(`/api/v1/trips/${id}/milestones`)
  ).json();
  expect(
    history.map((e: { milestone_type: string }) => e.milestone_type),
  ).toEqual(milestones);
  expect(
    history.every(
      (e: { occurred_at: string; recorded_at: string; recorded_by: string }) =>
        e.occurred_at && e.recorded_at && e.recorded_by,
    ),
  ).toBe(true);
  const logs = await (
    await page.request.get(
      `/api/v1/audit-logs?entity_type=trip&entity_id=${id}`,
    )
  ).json();
  expect(logs.map((e: { action: string }) => e.action)).toEqual(
    expect.arrayContaining([
      "trip.created",
      "trip.assigned",
      "trip.dispatched",
      "trip.transitioned",
      "trip.delivered",
      "trip.completed",
    ]),
  );
  expect(
    (
      await page.request.patch(`/api/v1/trips/${id}`, {
        headers,
        data: {
          ...tripBody(refs.customer),
          expected_version: completed.version,
        },
      })
    ).status(),
  ).toBe(409);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/batch4-trip-completed-${width}.png`,
      fullPage: true,
    });
  }
  const b = provision("Trip-B");
  await logout(page);
  await login(page, b.email);
  const refsB = await fleet(page, b);
  const own = await post(page.request, "/trips", tripBody(refsB.customer));
  for (const suffix of ["", "/milestones", "/assignments"])
    expect(
      (await page.request.get(`/api/v1/trips/${id}${suffix}`)).status(),
    ).toBe(404);
  const search = await (
    await page.request.get(`/api/v1/trips?search=${scheduled.trip_number}`)
  ).json();
  expect(search.items.every((t: Trip) => t.id !== id)).toBe(true);
  expect(search.total).toBe(1); // Tenant-local numbers intentionally repeat.
  expect(
    (
      await page.request.patch(`/api/v1/trips/${id}`, {
        headers,
        data: {
          ...tripBody(refsB.customer),
          expected_version: completed.version,
        },
      })
    ).status(),
  ).toBe(404);
  for (const [suffix, data] of [
    ["assign", { vehicle_id: refs.vehicle, driver_id: refs.driver }],
    ["transition", { action: "dispatch" }],
    ["cancel", { reason: "Attack" }],
    ["complete", { closeout_reviewed: true }],
  ] as const)
    expect(
      (
        await page.request.post(`/api/v1/trips/${id}/${suffix}`, {
          headers,
          data: { ...data, expected_version: completed.version },
        })
      ).status(),
    ).toBe(404);
  for (const [vehicle_id, driver_id] of [
    [refs.vehicle, refsB.driver],
    [refsB.vehicle, refs.driver],
  ])
    expect(
      (
        await page.request.post(`/api/v1/trips/${own.id}/assign`, {
          headers,
          data: { expected_version: own.version, vehicle_id, driver_id },
        })
      ).status(),
    ).toBe(404);
  await page.goto(`/trips/${id}`);
  await expect(
    page.getByRole("alert").filter({ hasText: "Record not found" }),
  ).toBeVisible();
  await logout(page);
  await login(page, b.driver_email, true);
  expect((await page.request.get(`/api/v1/driver/trips/${id}`)).status()).toBe(
    404,
  );
  expect(
    (await page.request.get(`/api/v1/driver/trips/${id}/milestones`)).status(),
  ).toBe(404);
  const bTrips = await (await page.request.get("/api/v1/driver/trips")).json();
  expect(bTrips.total).toBe(0);
  expect(bTrips.items).toEqual([]);
  expect(
    (
      await page.request.post(`/api/v1/driver/trips/${id}/transition`, {
        headers,
        data: { expected_version: completed.version, action: "start_pickup" },
      })
    ).status(),
  ).toBe(404);
  expect((await page.request.get("/api/v1/trips")).status()).toBe(403);
});

test("Batch 4 driver golden workflow: own assignment, valid next actions and closed trip", async ({
  page,
  browser,
}) => {
  test.setTimeout(150000);
  const a = provision("Driver-flow");
  await login(page, a.email);
  const refs = await fleet(page, a);
  let trip: Trip = await post(page.request, "/trips", {
    ...tripBody(refs.customer),
    vehicle_id: refs.vehicle,
    driver_id: refs.driver,
  });
  const unrelated: Trip = await post(
    page.request,
    "/trips",
    tripBody(refs.customer),
  );
  trip = await post(page.request, `/trips/${trip.id}/transition`, {
    action: "dispatch",
    expected_version: trip.version,
  });
  await logout(page);
  await login(page, a.driver_email, true);
  await page.setViewportSize({ width: 390, height: 900 });
  await expect(page.getByText(trip.trip_number, { exact: true })).toBeVisible();
  await expect(
    page.getByText(unrelated.trip_number, { exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("link", { name: "Start / en route to pickup", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: labels[1], exact: true }),
  ).toBeVisible();
  expect(
    (
      await page.request.post(`/api/v1/driver/trips/${trip.id}/transition`, {
        headers,
        data: { action: "deliver", expected_version: trip.version },
      })
    ).status(),
  ).toBe(409);
  expect(
    (await page.request.get(`/api/v1/driver/trips/${unrelated.id}`)).status(),
  ).toBe(404);
  await expect(
    page.getByText("Private operator note", { exact: true }),
  ).toHaveCount(0);
  page.on("dialog", (dialog) => dialog.accept());
  for (let index = 1; index < labels.length; index++)
    await uiAction(page, labels[index], labels[index + 1] ?? "");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/batch4-driver-delivered-390.png",
    fullPage: true,
  });
  const context = await browser.newContext();
  const owner = context.request;
  const response = await owner.post("http://localhost:3100/api/v1/auth/login", {
    headers,
    form: { username: a.email, password: process.env.DEMO_PASSWORD! },
  });
  expect(response.status()).toBe(204);
  trip = await (
    await page.request.get(`/api/v1/driver/trips/${trip.id}`)
  ).json();
  const deliveryHistory = await (
    await owner.get(
      `http://localhost:3100/api/v1/trips/${trip.id}/delivery-attempts`,
    )
  ).json();
  const review = await owner.post(
    `http://localhost:3100/api/v1/pod/${deliveryHistory.items[0].pod.id}/review`,
    { headers, data: { expected_version: trip.version } },
  );
  expect(review.status()).toBe(200);
  trip.version = (await review.json()).trip_version;
  const complete = await owner.post(
    `http://localhost:3100/api/v1/trips/${trip.id}/complete`,
    {
      headers,
      data: { expected_version: trip.version, closeout_reviewed: true },
    },
  );
  expect(complete.status()).toBe(200);
  await context.close();
  await page.reload();
  await expect(
    page.getByText("Trip completed. Operational details are read-only.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Mark delivered", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Complete trip", exact: true }),
  ).toHaveCount(0);
  await page.goto("/driver/trips");
  await expect(
    page.getByText("No assigned trips", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Trip history", exact: true }).click();
  await expect(page.getByText(trip.trip_number, { exact: true })).toBeVisible();
});

test("Dispatch cancellation, filters, error recovery and mobile creation", async ({
  page,
}) => {
  test.setTimeout(90000);
  const a = provision("Cancel-flow");
  await login(page, a.email);
  const refs = await fleet(page, a);
  const trip: Trip = await post(
    page.request,
    "/trips",
    tripBody(refs.customer),
  );
  await page.goto(`/trips/${trip.id}`);
  page.on("dialog", (dialog) => dialog.accept());
  await page
    .getByLabel("Cancellation reason", { exact: true })
    .fill("Customer rescheduled shipment");
  await page.getByRole("button", { name: "Cancel trip", exact: true }).click();
  await expect(
    page.getByText("Trip cancelled. It cannot be resumed.", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("Customer rescheduled shipment", { exact: true }).first(),
  ).toBeVisible();
  await page.goto("/dispatch");
  await page.getByRole("button", { name: "Cancelled", exact: true }).click();
  await expect(
    page.getByRole("link", { name: trip.trip_number, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Status", exact: true })
    .selectOption("COMPLETED");
  await expect(
    page.getByText("No trips in this view", { exact: true }),
  ).toBeVisible();
  await page.route("**/api/v1/dispatch?**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: { message: "Dispatch temporarily unavailable" },
      }),
    }),
  );
  await page.reload();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Dispatch temporarily unavailable" }),
  ).toBeVisible();
  await page.unroute("**/api/v1/dispatch?**");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByText("No trips in this view", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 360, height: 900 });
  await page.goto("/trips/new");
  await expect(
    page.getByRole("heading", { name: "Create trip", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/batch4-trip-form-360.png",
    fullPage: true,
  });
});
