import { test, expect, type Locator } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { expectLockedV1 } from "./design-v1";

test("cash settlement golden, partial balance and post-approval correction retain immutable history", async ({
  page,
}) => {
  test.setTimeout(180000);
  const fixture = JSON.parse(
    execFileSync(
      resolve(".venv/Scripts/python.exe"),
      ["scripts/api-task.py", "--test", "tests.e2e_governance"],
      { encoding: "utf8", timeout: 60000 },
    ),
  );
  await page.goto("/login");
  await page.getByLabel("Email address").fill(fixture.email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/dashboard/);
  const financial = page.locator(".financial-panel"),
    panel = page.locator(".governance-panel");
  async function save(form: Locator) {
    await form
      .getByLabel(
        "I confirm this permanent financial entry. Original records remain in history.",
      )
      .check();
    await form.getByRole("button", { name: "Save settlement entry" }).click();
    await expect(form).toHaveCount(0);
  }
  async function issue() {
    await panel
      .getByRole("button", { name: "Issue cash advance", exact: true })
      .click();
    const form = panel.locator("form");
    await form.getByLabel("Cash amount (PHP)").fill("5000.00");
    await save(form);
  }
  async function apply(id: string) {
    await panel
      .getByRole("button", { name: "Apply expense", exact: true })
      .click();
    const form = panel.locator("form");
    await form
      .getByRole("combobox", { name: "Expense record", exact: true })
      .selectOption(id);
    await form
      .getByLabel("Settlement reason")
      .fill("Reviewed receipt applied to advance.");
    await save(form);
  }
  async function cash(value: string) {
    await panel
      .getByRole("button", { name: "Record cash return", exact: true })
      .click();
    const form = panel.locator("form");
    await form.getByLabel("Cash amount (PHP)").fill(value);
    await form
      .getByLabel("Settlement reason")
      .fill("Unused cash returned and verified.");
    await save(form);
  }
  async function approve() {
    await panel
      .getByLabel(
        "I have checked revenue, costs, adjustments and advances, and all known financial records have synchronized.",
      )
      .check();
    await panel
      .getByRole("button", { name: "Approve financial review", exact: true })
      .click();
    await expect(financial.getByText("FINAL", { exact: true })).toBeVisible();
  }
  await page.goto(`/trips/${fixture.trips[0].trip.id}`);
  await expect(panel.getByText("No cash advances recorded.")).toBeVisible();
  await issue();
  await expect(
    panel.getByText("Cash advance remains outstanding."),
  ).toBeVisible();
  for (const id of fixture.trips[0].expenses) await apply(id);
  await cash("1800.00");
  await expect(panel.getByText("Settled", { exact: true })).toBeVisible();
  await expect(panel.getByText("₱0.00", { exact: true })).toBeVisible();
  await expect(
    financial.getByText("₱16,800.00", { exact: true }),
  ).toBeVisible();
  await approve();
  await page.reload();
  await expect(financial.getByText("FINAL", { exact: true })).toBeVisible();
  const response = await page.request.post(
    `/api/v1/trips/${fixture.trips[0].trip.id}/adjustments`,
    {
      headers: {
        Origin: "http://localhost:3100",
        "Idempotency-Key": randomUUID(),
      },
      data: {
        target_id: fixture.trips[0].expenses[1],
        adjustment_type: "AMOUNT_CORRECTION",
        new_value: "1200.00",
        expected_sequence: 0,
        reason: "Receipt verified after financial review.",
      },
    },
  );
  expect(response.ok(), await response.text()).toBe(true);
  await page.reload();
  await expect(
    financial.getByText("PROVISIONAL", { exact: true }),
  ).toBeVisible();
  await expect(
    financial.getByText("₱16,300.00", { exact: true }),
  ).toBeVisible();
  await expect(
    panel.getByText(/Financial records changed: closed trip adjustments/),
  ).toBeVisible();
  await approve();
  await expectLockedV1(page, false);
  await page.screenshot({
    path: "test-results/batch14-settlement-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("body")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/batch14-settlement-mobile.png",
    fullPage: true,
  });
  await page.goto(`/trips/${fixture.trips[1].trip.id}`);
  await issue();
  await apply(fixture.trips[1].expenses[0]);
  await cash("1000.00");
  await expect(
    panel.getByText("Partially settled", { exact: true }),
  ).toBeVisible();
  await expect(
    panel.getByText("Cash advance remains outstanding."),
  ).toBeVisible();
  await expect(
    financial.getByText("PROVISIONAL", { exact: true }),
  ).toBeVisible();
  await panel.getByLabel(/I have checked revenue/).check();
  await expect(
    panel.getByRole("button", {
      name: "Approve financial review",
      exact: true,
    }),
  ).toBeDisabled();
  const state = await (
    await page.request.get(
      `/api/v1/trips/${fixture.trips[1].trip.id}/financial-review`,
    )
  ).json();
  const denied = await page.request.post(
    `/api/v1/trips/${fixture.trips[1].trip.id}/financial-review/approve`,
    {
      headers: {
        Origin: "http://localhost:3100",
        "Idempotency-Key": randomUUID(),
      },
      data: {
        expected_event_id: state.latest_event_id,
        records_confirmed: true,
      },
    },
  );
  expect(denied.status()).toBe(409);
});
