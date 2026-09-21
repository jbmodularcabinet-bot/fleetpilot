import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expectLockedV1 } from "./design-v1";

const reports = [
  ["executive-contribution", "Executive Contribution"],
  ["trip-contribution", "Trip Contribution"],
  ["customer-contribution", "Customer Contribution"],
  ["direct-cost-analysis", "Direct Cost Analysis"],
  ["financial-exceptions", "Financial Exceptions"],
  ["cash-advance-settlement", "Cash Advance & Settlement"],
] as const;

test("owner Dashboard, Intelligence and six Reports follow the locked source of truth", async ({
  page,
}) => {
  test.setTimeout(180000);
  const fixture = JSON.parse(
    execFileSync(
      resolve(
        process.platform === "win32"
          ? ".venv/Scripts/python.exe"
          : ".venv/bin/python",
      ),
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
  await expect(
    page.getByText("Reviewed Revenue", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Direct Cost", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Contribution", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Weighted Margin", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Intelligence Brief", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Dashboard summaries unavailable")).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("link", { name: "Intelligence", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Reports", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/mvp1-dashboard-1440.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  await page.goto("/intelligence");
  await expect(
    page.getByRole("heading", { name: "FleetPilot Intelligence" }),
  ).toBeVisible();
  await expect(page.getByText("OWNER BRIEF", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Evidence Standard", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/mvp1-intelligence-1440.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  await page.goto("/reports");
  for (const [, title] of reports) {
    await expect(
      page.getByRole("link", { name: new RegExp(title) }),
    ).toBeVisible();
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  for (const [slug, title] of reports) {
    await page.goto(`/reports/${slug}`);
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(
      page.getByText("Basis: REVIEWED_EFFECTIVE", { exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }

  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto("/dashboard");
  await expect(
    page.getByText("Reviewed Revenue", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/mvp1-dashboard-1024.png",
    fullPage: true,
  });

  await page.goto("/reports/executive-contribution");
  await expect(
    page.getByRole("heading", { name: "Executive Contribution" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/mvp1-executive-report-1024.png",
    fullPage: true,
  });

  await page.goto(`/trips/${fixture.trips[0].trip.id}`);
  await expectLockedV1(page, false);
});
