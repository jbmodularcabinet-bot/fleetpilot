import {
  test,
  expect,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { expectLockedV1 } from "./design-v1";
test.setTimeout(150000);
const headers = { Origin: "http://localhost:3100" };
function provision(label: string) {
  return JSON.parse(
    execFileSync(
      resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
      ["scripts/api-task.py", "--test", "tests.e2e_setup", label, "--driver"],
      { encoding: "utf8", timeout: 60000 },
    ),
  ) as { email: string; driver_email: string; driver_user_id: string };
}
async function login(page: Page, email: string, driver = false) {
  await page.request.post("/api/v1/auth/logout", { headers });
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(driver ? /\/driver$/ : /\/dashboard$/);
}
async function post(api: APIRequestContext, path: string, data: unknown) {
  const r = await api.post("/api/v1" + path, {
    headers: { ...headers, "Idempotency-Key": randomUUID() },
    data,
  });
  expect(r.ok(), await r.text()).toBe(true);
  return r.json();
}
async function prepare(page: Page, label: string) {
  const fixture = provision(label);
  await login(page, fixture.email);
  const vehicle = await post(page.request, "/vehicles", {
    unit_number: "TRK-001",
    plate_number: "ABC-1234",
    vehicle_type: "Wing van",
    odometer: "48000",
  });
  const driver = await post(page.request, "/drivers", {
    employee_number: "JUAN",
    first_name: "Juan",
    last_name: "Dela Cruz",
    user_id: fixture.driver_user_id,
  });
  return { fixture, vehicle, driver };
}

test("Preventive maintenance golden preserves native Fleet UI and exact service history", async ({
  page,
}) => {
  for (const path of ["health", "ready"]) {
    const response = await page.request.get(`http://127.0.0.1:8100/${path}`);
    expect(response.status()).toBe(200);
  }
  const { vehicle } = await prepare(page, "maintenance-owner");
  await page.goto("/fleet/vehicles/" + vehicle.id);
  await page.getByText("Create maintenance schedule", { exact: true }).click();
  await page.getByLabel("Every km", { exact: true }).fill("5000");
  await page.getByLabel("Last service odometer", { exact: true }).fill("45000");
  await page.getByLabel("Warning km", { exact: true }).fill("1000");
  await page
    .getByRole("button", { name: "Save schedule", exact: true })
    .click();
  await expect(page.getByText("Maintenance schedule created.")).toBeVisible();
  await expect(page.getByText("Next service: 50000.0 km")).toBeVisible();
  await page.getByText("Create work order", { exact: true }).click();
  await page.getByLabel("Work order title").fill("Engine oil service");
  await page
    .getByLabel("Work description")
    .fill("Replace engine oil and filter");
  const sch = await page.request.get(
    "/api/v1/vehicles/" + vehicle.id + "/maintenance",
  );
  const sid = (await sch.json()).schedules[0].id;
  await page.getByLabel("Source schedule").selectOption(sid);
  await page.getByLabel("Requires vehicle downtime").check();
  await page
    .getByRole("button", { name: "Save work order", exact: true })
    .click();
  await expect(page.getByText("Work order created.")).toBeVisible();
  await page.getByRole("link", { name: /WO-000001/ }).click();
  await page.getByLabel("Work order action").selectOption("start");
  await page.getByRole("button", { name: "Apply work order action" }).click();
  await expect(page.getByText("Maintenance record saved.")).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/vehicles/" + vehicle.id)).json())
      .status,
  ).toBe("MAINTENANCE");
  for (const [kind, amount] of [
    ["PART", "1234.56"],
    ["LABOR", "500.00"],
    ["OTHER", "100.10"],
  ]) {
    await page.getByLabel("Cost type").selectOption(kind);
    await page.getByLabel("Cost description").fill(kind);
    await page.getByLabel("Unit cost PHP").fill(amount);
    await page.getByRole("button", { name: "Add maintenance cost" }).click();
    await expect(page.getByText(new RegExp(kind + " ·", "i"))).toBeVisible();
  }
  await expect(page.getByText("Maintenance cost: ₱1,834.66")).toBeVisible();
  await page
    .getByLabel("Evidence image")
    .setInputFiles("tests/fixtures/delivery.png");
  await page
    .getByRole("button", { name: "Upload evidence", exact: true })
    .click();
  await expect(page.getByText("Evidence uploaded.")).toBeVisible();
  await page.getByLabel("Completion odometer").fill("50250");
  await page
    .getByLabel("Work performed", { exact: true })
    .fill("Oil and filter replaced");
  await page.getByRole("button", { name: "Apply work order action" }).click();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Maintenance cost: ₱1,834.66")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Add maintenance cost" }),
  ).toHaveCount(0);
  await expectLockedV1(page, false, "Work order");
  await page.screenshot({
    path: "test-results/batch11-maintenance-owner.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/batch11-maintenance-owner-mobile.png", fullPage: true });
  const history = await (
    await page.request.get("/api/v1/vehicles/" + vehicle.id + "/maintenance")
  ).json();
  expect(history.schedules[0].next_due_odometer).toBe("55250.0");
  expect(
    (await (await page.request.get("/api/v1/vehicles/" + vehicle.id)).json())
      .status,
  ).toBe("AVAILABLE");
  await page.goto("/maintenance");
  await page.getByLabel("Maintenance view").selectOption("history");
  await expect(page.getByRole("link", { name: /WO-000001/ })).toBeVisible();
});

test("Offline driver defect and photo survive reopen and lost response, then repair resolves original report", async ({
  page,
  context,
}) => {
  const { fixture, vehicle, driver } = await prepare(
    page,
    "maintenance-driver",
  );
  await post(page.request, "/vehicle-driver-assignments", {
    vehicle_id: vehicle.id,
    driver_id: driver.id,
  });
  await login(page, fixture.driver_email, true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Report vehicle issue", exact: true })
    .click();
  await expect(page.getByRole("option", { name: "TRK-001" })).toHaveCount(1);
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
  await page
    .getByRole("button", { name: "Report vehicle issue", exact: true })
    .click();
  await page.getByLabel("Assigned vehicle").selectOption(vehicle.id);
  await context.setOffline(true);
  await page.getByLabel("Severity").selectOption("SERIOUS");
  await page.getByLabel("Defect category").selectOption("BRAKES");
  await page
    .getByLabel("Defect description")
    .fill("Brake pedal feels softer than normal.");
  await page
    .getByLabel("Defect photos")
    .setInputFiles("tests/fixtures/delivery.png");
  await page.getByRole("button", { name: "Save vehicle issue" }).click();
  await expect(
    page.getByText(/Saved locally. Check sync status/),
  ).toBeVisible();
  await page.close();
  const reopened = await context.newPage();
  await reopened.setViewportSize({ width: 390, height: 844 });
  await reopened.goto("/driver");
  await reopened.getByText("Saved work (2)", { exact: true }).click();
  await expect(
    reopened.getByRole("link", { name: "Vehicle defect report", exact: true }),
  ).toBeVisible();
  await expect(
    reopened.getByRole("link", { name: "Defect photo: delivery.png" }),
  ).toBeVisible();
  await expectLockedV1(reopened, true, "Vehicle issue");
  expect(
    await reopened.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await reopened.screenshot({
    path: "test-results/batch11-defect-offline.png",
    fullPage: true,
  });
  let dropped = false,
    replayed = false,
    key = "";
  await context.route("**/api/v1/driver/defects", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const r = await route.fetch();
    expect(r.status()).toBe(200);
    if (!dropped) {
      dropped = true;
      key = route.request().headers()["idempotency-key"];
      await route.abort("failed");
    } else {
      if (route.request().headers()["idempotency-key"] === key) {
        expect((await r.json()).outcome).toBe("ALREADY_APPLIED");
        replayed = true;
      }
      await route.fulfill({ response: r });
    }
  });
  await context.setOffline(false);
  await expect(reopened.getByText(/Synced · no pending actions/)).toBeVisible({
    timeout: 60000,
  });
  expect(dropped && replayed).toBe(true);
  const defects = await (
    await reopened.request.get("/api/v1/driver/defects")
  ).json();
  expect(defects.items).toHaveLength(1);
  const defect = defects.items[0];
  const detail = await (
    await reopened.request.get("/api/v1/defects/" + defect.id)
  ).json();
  expect(detail.evidence).toHaveLength(1);
  await login(reopened, fixture.email);
  await reopened.goto("/fleet/vehicles/" + vehicle.id);
  await reopened
    .getByLabel("Review / dismissal reason")
    .fill("Inspect braking system");
  await reopened.getByRole("button", { name: "Apply defect action" }).click();
  await expect(reopened.getByText("Reviewed", { exact: true })).toBeVisible();
  await reopened.getByLabel("Defect action").selectOption("work");
  await reopened.getByRole("button", { name: "Apply defect action" }).click();
  await expect(reopened.getByRole("link", { name: /WO-000001/ })).toBeVisible();
  await reopened.getByRole("link", { name: /WO-000001/ }).click();
  await reopened.getByLabel("Work order action").selectOption("start");
  await reopened
    .getByRole("button", { name: "Apply work order action" })
    .click();
  await expect(reopened.getByLabel("Work order action")).toHaveValue(
    "complete",
  );
  await reopened.getByLabel("Completion odometer").fill("48000");
  await reopened
    .getByLabel("Work performed", { exact: true })
    .fill("Brake hydraulics inspected and repaired");
  await reopened
    .getByRole("button", { name: "Apply work order action" })
    .click();
  await expect(reopened.getByText("Completed", { exact: true })).toBeVisible();
  const final = await (
    await reopened.request.get("/api/v1/defects/" + defect.id)
  ).json();
  expect(final.description).toBe("Brake pedal feels softer than normal.");
  expect(final.status).toBe("RESOLVED");
  expect(final.evidence).toHaveLength(1);
});
