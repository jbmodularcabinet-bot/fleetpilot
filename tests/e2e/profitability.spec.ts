import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { expectLockedV1 } from "./design-v1";

test("profitability golden: reviewed contribution, immutable corrections, maintenance exclusion and list", async ({
  page,
}) => {
  test.setTimeout(150000);
  const fixture = JSON.parse(
    execFileSync(
      resolve(".venv/Scripts/python.exe"),
      ["scripts/api-task.py", "--test", "tests.e2e_profitability"],
      { encoding: "utf8", timeout: 60000 },
    ),
  );
  await page.goto("/login");
  await page.getByLabel("Email address").fill("carlo@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/dashboard/);
  await page.goto(`/trips/${fixture.trip.id}`);
  const panel = page.locator(".financial-panel");
  await expect(panel.getByText("No revenue recorded yet.")).toBeVisible();
  await panel.getByRole("button", { name: "Add revenue", exact: true }).click();
  await panel.getByLabel("Revenue amount (PHP)").fill("25000.00");
  await panel.getByLabel("Revenue reference").fill("Operational charge 001");
  await panel.getByRole("button", { name: "Save revenue" }).click();
  await expect(panel.getByText("PROVISIONAL", { exact: true })).toBeVisible();
  await panel
    .getByRole("button", { name: "Review revenue", exact: true })
    .click();
  // Batch 14 adds explicit trip approval; retain the original FINAL and money assertions.
  await panel
    .getByLabel(
      "I have checked revenue, costs, adjustments and advances, and all known financial records have synchronized.",
    )
    .check();
  await panel
    .getByRole("button", { name: "Approve financial review", exact: true })
    .click();
  await expect(panel.getByText("FINAL", { exact: true })).toBeVisible();
  await expect(panel.getByText("₱14,700.00", { exact: true })).toBeVisible();
  await expect(panel.getByText("58.80%", { exact: true })).toBeVisible();
  const headers = {
    Origin: "http://localhost:3100",
    "Idempotency-Key": randomUUID(),
  };
  const adjustment = await page.request.post(
    `/api/v1/trips/${fixture.trip.id}/adjustments`,
    {
      headers,
      data: {
        target_id: fixture.expenses[1],
        expected_sequence: 0,
        adjustment_type: "AMOUNT_CORRECTION",
        new_value: "1500.00",
        reason: "Receipt verified after trip close.",
      },
    },
  );
  expect(adjustment.ok(), await adjustment.text()).toBe(true);
  await page.reload();
  await expect(panel.getByText("₱14,200.00", { exact: true })).toBeVisible();
  await expect(panel.getByText("56.80%", { exact: true })).toBeVisible();
  const work = await page.request.post("/api/v1/maintenance/work-orders", {
    headers: { ...headers, "Idempotency-Key": randomUUID() },
    data: {
      vehicle_id: fixture.vehicle,
      trip_id: fixture.trip.id,
      type: "REPAIR",
      title: "Linked service",
      description: "Separate maintenance cost",
      requires_vehicle_downtime: false,
    },
  });
  expect(work.ok(), await work.text()).toBe(true);
  const w = (await work.json()).result.work_order;
  const cost = await page.request.post(
    `/api/v1/maintenance/work-orders/${w.id}/cost-items`,
    {
      headers: { ...headers, "Idempotency-Key": randomUUID() },
      data: {
        type: "PART",
        description: "Separate maintenance",
        unit_cost: "12000.00",
      },
    },
  );
  expect(cost.ok(), await cost.text()).toBe(true);
  await panel
    .getByRole("button", { name: "Adjust revenue", exact: true })
    .click();
  await panel.getByLabel("Revenue amount (PHP)").fill("26000.00");
  await panel
    .getByLabel("Revenue correction reason")
    .fill("Approved operational surcharge.");
  await panel.getByLabel(/This will not overwrite/).check();
  await panel.getByRole("button", { name: "Confirm revenue change" }).click();
  await expect(panel.getByText("₱15,200.00", { exact: true })).toBeVisible();
  await page.reload();
  await expect(panel.getByText("₱10,800.00", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "View revenue history" }).click();
  await expect(panel.getByText(/Approved operational surcharge/)).toBeVisible();
  await expect(panel.getByText(/Original ₱25,000.00/)).toBeVisible();
  await expectLockedV1(page, false);
  await page.screenshot({
    path: "test-results/batch13-financials-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/batch13-financials-mobile.png",
    fullPage: true,
  });
  await panel
    .getByRole("link", { name: "View trip contribution list" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Trip contribution", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "₱15,200.00", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Search financial trips").fill("not-a-trip");
  await expect(
    page.getByText("No matching trips", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Search financial trips")
    .fill(fixture.trip.trip_number);
  await expect(
    page.getByRole("link", { name: fixture.trip.trip_number, exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const original = await page.request.get(
    `/api/v1/expenses/${fixture.expenses[1]}`,
  );
  expect((await original.json()).current.amount).toBe("1000.00");
  await page.request.post("/api/v1/auth/logout", {
    headers: { Origin: "http://localhost:3100" },
  });
  await page.request.post("/api/v1/auth/login", {
    headers: { Origin: "http://localhost:3100" },
    form: {
      username: "juan@example.com",
      password: process.env.DEMO_PASSWORD!,
    },
  });
  expect(
    (
      await page.request.get(`/api/v1/trips/${fixture.trip.id}/financials`)
    ).status(),
  ).toBe(403);
  await page.goto(`/driver/trips/${fixture.trip.id}`);
  await expect(
    page.getByRole("heading", { name: fixture.trip.trip_number, exact: true }),
  ).toBeVisible();
  await expect(page.locator(".financial-panel")).toHaveCount(0);
});
