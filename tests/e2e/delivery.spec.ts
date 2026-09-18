import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expectLockedV1 } from "./design-v1";

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
async function signature(page: Page) {
  const canvas = page.getByLabel("Recipient signature drawing area");
  await canvas.evaluate((element) =>
    element.scrollIntoView({ block: "center" }),
  );
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + 15, box!.y + 35);
  await page.mouse.down();
  await page.mouse.move(box!.x + 55, box!.y + 65, { steps: 8 });
  await page.mouse.move(box!.x + 90, box!.y + 20, { steps: 8 });
  await page.mouse.up();
  await page
    .getByRole("checkbox", {
      name: "Recipient confirms this signature",
      exact: true,
    })
    .check();
}
async function confirmDelivery(
  page: Page,
  withSignature = true,
  recipient = "Maria Santos",
) {
  await page
    .getByRole("button", { name: "Confirm delivery", exact: true })
    .click();
  await expectLockedV1(page, true);
  await expect(
    page.getByRole("button", { name: "Submit proof of delivery", exact: true }),
  ).toHaveCSS("background-color", "rgb(43, 224, 167)");
  await expect(
    page.getByLabel("Recipient name", { exact: true }),
  ).toHaveAttribute("required", "");
  await page.getByLabel("Recipient name", { exact: true }).fill(recipient);
  await page
    .getByLabel("Recipient role", { exact: true })
    .fill("Receiving Staff");
  await page
    .getByLabel("Delivery photos (at least one required)")
    .setInputFiles("tests/fixtures/delivery.png");
  if (withSignature) {
    await signature(page);
    await page
      .getByRole("button", { name: "Clear signature", exact: true })
      .click();
    await expect(
      page.getByRole("checkbox", { name: "Recipient confirms this signature" }),
    ).not.toBeChecked();
    await signature(page);
  }
  await page
    .getByLabel("Delivery notes", { exact: true })
    .fill("Cargo received in good condition.");
  await page
    .getByRole("checkbox", {
      name: "I confirm the cargo was delivered to this recipient.",
      exact: true,
    })
    .check();
  await page
    .getByRole("button", { name: "Submit proof of delivery", exact: true })
    .click();
  await expect(
    page.getByText("Delivery confirmed. Awaiting operator closeout.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(`Received by ${recipient}`, { exact: true }),
  ).toBeVisible();
}
async function closeout(
  page: Page,
  fixture: Fixture,
  trip: Trip,
  recipient = "Maria Santos",
) {
  await login(page, fixture.email);
  await page.goto(`/trips/${trip.id}`);
  await expect(
    page.getByText(`Received by ${recipient}`, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Complete trip", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Review POD", exact: true }).click();
  await expect(page.getByText(/POD Reviewed/)).toBeVisible();
  await page
    .getByRole("checkbox", {
      name: "I reviewed the required trip details and milestone history.",
      exact: true,
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
  await expect(page.getByText(/POD Reviewed/)).toBeVisible();
}

test("Batch 5 successful delivery: driver photo/signature, owner review, closeout and evidence isolation", async ({
  page,
}) => {
  test.setTimeout(180000);
  const a = provision("POD-Success");
  const trip = await prepare(page, a);
  page.on("dialog", (dialog) => dialog.accept());
  await login(page, a.driver_email, true);
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto(`/driver/trips/${trip.id}`);
  await confirmDelivery(page);
  const history = await (
    await page.request.get(`/api/v1/trips/${trip.id}/delivery-attempts`)
  ).json();
  const attempt = history.items[0];
  expect(attempt.status).toBe("DELIVERED");
  expect(attempt.pod.status).toBe("SUBMITTED");
  expect(attempt.evidence).toHaveLength(2);
  for (const evidence of attempt.evidence) {
    expect(evidence.storage_key).toBeUndefined();
    const image = await page.request.get(`/api/v1/evidence/${evidence.id}`);
    expect(image.status()).toBe(200);
    expect(image.headers()["content-type"]).toBe("image/png");
  }
  await expect(
    page.getByRole("img", { name: "Signature", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/batch5-driver-pod-390.png",
    fullPage: true,
  });
  await closeout(page, a, trip);
  const persisted = await (
    await page.request.get(`/api/v1/trips/${trip.id}/delivery-attempts`)
  ).json();
  expect(persisted.items[0].pod.reviewed_at).toBeTruthy();
  expect(persisted.items[0].pod.reviewed_by).toBeTruthy();
  expect(persisted.items[0].evidence).toHaveLength(2);
  const logs = await (
    await page.request.get(
      `/api/v1/audit-logs?entity_type=trip&entity_id=${trip.id}&limit=100`,
    )
  ).json();
  expect(logs.map((r: { action: string }) => r.action)).toEqual(
    expect.arrayContaining([
      "pod.submitted",
      "pod.reviewed",
      "evidence.uploaded",
      "delivery_attempt.delivered",
      "trip.completed",
    ]),
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expectLockedV1(page, false);
  await page.screenshot({
    path: "test-results/batch5-owner-pod-1440.png",
    fullPage: true,
  });
  const b = provision("POD-Foreign");
  await login(page, b.email);
  for (const path of [
    `/trips/${trip.id}/delivery-attempts`,
    `/delivery-attempts/${attempt.id}`,
    `/pod/${attempt.pod.id}`,
    ...attempt.evidence.map((r: { id: string }) => `/evidence/${r.id}`),
  ])
    expect((await page.request.get(`/api/v1${path}`)).status()).toBe(404);
  expect(
    (
      await page.request.post(`/api/v1/pod/${attempt.pod.id}/review`, {
        headers,
        data: { expected_version: persisted.trip_version },
      })
    ).status(),
  ).toBe(404);
  await login(page, b.driver_email, true);
  for (const evidence of attempt.evidence)
    expect(
      (await page.request.get(`/api/v1/evidence/${evidence.id}`)).status(),
    ).toBe(404);
  expect(
    (
      await page.request.post(
        `/api/v1/delivery-attempts/${attempt.id}/exception`,
        {
          headers,
          data: {
            expected_version: 1,
            exception_type: "OTHER",
            notes: "Forbidden",
          },
        },
      )
    ).status(),
  ).toBe(404);
});

test("Batch 5 failed delivery: immutable first attempt, operator retry and later successful POD", async ({
  page,
}) => {
  test.setTimeout(180000);
  const a = provision("POD-Retry");
  let trip = await prepare(page, a, "arrive_delivery");
  page.on("dialog", (dialog) => dialog.accept());
  await login(page, a.driver_email, true);
  await page.setViewportSize({ width: 360, height: 900 });
  await page.goto(`/driver/trips/${trip.id}`);
  await page
    .getByRole("button", { name: "Report delivery issue", exact: true })
    .click();
  await page
    .getByLabel("Delivery issue", { exact: true })
    .selectOption("OTHER");
  await expect(
    page.getByLabel("Exception notes", { exact: true }),
  ).toHaveAttribute("required", "");
  await page
    .getByLabel("Delivery issue", { exact: true })
    .selectOption("RECIPIENT_UNAVAILABLE");
  await page
    .getByLabel("Exception notes", { exact: true })
    .fill("Recipient contact unreachable.");
  await page
    .getByLabel("Exception photos (optional)")
    .setInputFiles("tests/fixtures/delivery.png");
  await page
    .getByRole("button", { name: "Submit delivery issue", exact: true })
    .click();
  await expect(
    page.getByText(
      "Delivery issue reported. Awaiting operator retry authorization. This trip is not delivered.",
      { exact: true },
    ),
  ).toBeVisible();
  const first = (
    await (
      await page.request.get(`/api/v1/trips/${trip.id}/delivery-attempts`)
    ).json()
  ).items[0];
  expect(first.status).toBe("FAILED");
  expect(first.pod).toBeNull();
  expect(first.evidence).toHaveLength(1);
  trip = await (
    await page.request.get(`/api/v1/driver/trips/${trip.id}`)
  ).json();
  expect(trip.current_status).toBe("IN_TRANSIT");
  expect(
    (
      await page.request.post(`/api/v1/driver/trips/${trip.id}/transition`, {
        headers,
        data: { expected_version: trip.version, action: "start_unloading" },
      })
    ).status(),
  ).toBe(409);
  expect(
    (
      await page.request.post(
        `/api/v1/delivery-exceptions/${first.exception.id}/resolve`,
        {
          headers,
          data: {
            expected_version: trip.version,
            resolution_notes: "Driver cannot authorize retry",
          },
        },
      )
    ).status(),
  ).toBe(403);
  await page.screenshot({
    path: "test-results/batch5-driver-exception-360.png",
    fullPage: true,
  });
  await login(page, a.email);
  await page.goto(`/trips/${trip.id}`);
  await page
    .getByLabel("Retry authorization notes", { exact: true })
    .fill("Recipient is now present. Retry at this same delivery stop.");
  await page
    .getByRole("button", { name: "Authorize delivery retry", exact: true })
    .click();
  await expect(
    page.getByText(/Retry authorized at this delivery stop/),
  ).toBeVisible();
  await login(page, a.driver_email, true);
  await page.goto(`/driver/trips/${trip.id}`);
  await page
    .getByRole("button", { name: "Start unloading", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Unloading complete", exact: true })
    .click();
  await confirmDelivery(page, false, "Pedro Reyes");
  await closeout(page, a, trip, "Pedro Reyes");
  const history = await (
    await page.request.get(`/api/v1/trips/${trip.id}/delivery-attempts`)
  ).json();
  expect(history.total).toBe(2);
  expect(history.items[0].status).toBe("DELIVERED");
  expect(history.items[1].status).toBe("FAILED");
  expect(history.items[1].exception.notes).toBe(
    "Recipient contact unreachable.",
  );
  expect(history.items[1].evidence[0].id).toBe(first.evidence[0].id);
  expect(
    (
      await page.request.get(`/api/v1/evidence/${first.evidence[0].id}`)
    ).status(),
  ).toBe(200);
  const milestones = await (
    await page.request.get(`/api/v1/trips/${trip.id}/milestones`)
  ).json();
  expect(
    milestones.map((r: { milestone_type: string }) => r.milestone_type),
  ).toEqual(
    expect.arrayContaining([
      "DELIVERY_ATTEMPT_FAILED",
      "DELIVERY_RETRY_AUTHORIZED",
      "DELIVERY_RETRY_STARTED",
      "DELIVERED",
      "COMPLETED",
    ]),
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/batch5-attempt-history-360.png",
    fullPage: true,
  });
});
