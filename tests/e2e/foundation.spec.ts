import { test, expect, type Page } from "@playwright/test";
import { php } from "../../apps/web/src/lib/money";

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}
test("owner login, dashboard, settings save and persistence", async ({
  page,
}) => {
  const overviewResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/intelligence/overview") &&
      response.request().method() === "GET",
  );
  await login(page, "carlo@example.com");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("heading", { name: "Owner Dashboard" }),
  ).toBeVisible();
  const response = await overviewResponse;
  expect(response.status()).toBe(200);
  const report = await response.json();
  expect(report.scope.date_basis).toBe("Scheduled pickup date");
  expect(report.scope.fingerprint).toMatch(/^[a-f0-9]{64}$/);
  await expect(page.getByTestId("Reviewed Revenue")).toHaveText(
    php(report.summary.revenue),
  );
  await expect(page.getByTestId("Direct Trip Cost")).toHaveText(
    php(report.summary.direct_cost),
  );
  await expect(page.getByTestId("Contribution")).toHaveText(
    php(report.summary.contribution),
  );
  await expect(page.getByTestId("Weighted Contribution Margin")).toHaveText(
    report.summary.weighted_margin_percent === null
      ? "N/A"
      : `${report.summary.weighted_margin_percent}%`,
  );
  await expect(page.getByTestId("Negative-Contribution Trips")).toHaveText(
    String(report.summary.negative_count),
  );
  await expect(
    page.getByTestId("Trips Requiring Financial Attention"),
  ).toHaveText(String(report.summary.attention_trip_count));
  await expect(page.locator(".reporting-qualification")).toContainText(
    "not net profit or cash collected",
  );
  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await expect(
    navigation.getByRole("link", { name: "Intelligence", exact: true }),
  ).toBeVisible();
  await expect(
    navigation.getByRole("link", { name: "Reports", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  const input = page.getByLabel("Organization name", { exact: true });
  const original = await input.inputValue();
  await input.fill("Demo Logistics — E2E");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Organization details saved",
  );
  await page.reload();
  await expect(input).toHaveValue("Demo Logistics — E2E");
  await input.fill(original);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status")).toContainText("saved");
  await page.getByRole("link", { name: "People & access" }).click();
  await expect(page.getByText("Juan Dela Cruz")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});
test("driver login has no admin navigation and protected route boundary", async ({
  page,
}) => {
  await login(page, "juan@example.com");
  await expect(page).toHaveURL(/\/driver$/);
  await expect(
    page.getByRole("navigation", { name: "Driver navigation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Waiting for your first trip" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("link", { name: "Settings", exact: true }),
  ).toHaveCount(0);
  await page.goto("/settings/users");
  await expect(page).toHaveURL(/\/driver$/);
  await page.getByRole("link", { name: "Profile", exact: true }).click();
  await expect(page.getByText("Juan Dela Cruz", { exact: true })).toBeVisible();
});
for (const width of [360, 390, 430]) {
  test(`driver shell fits ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await login(page, "juan@example.com");
    await expect(page).toHaveURL(/\/driver$/);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await expect(
      page.getByRole("navigation", { name: "Driver navigation" }),
    ).toBeVisible();
    await page.screenshot({
      path: `test-results/driver-${width}.png`,
      fullPage: true,
    });
  });
}
test("owner layout fits laptop and desktop", async ({ page }) => {
  await login(page, "carlo@example.com");
  for (const width of [1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect(
      page.getByRole("heading", { name: "Owner Dashboard" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/owner-${width}.png`,
      fullPage: true,
    });
  }
});
test("bad password stays on login with actionable error", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email address").fill("carlo@example.com");
  await page.getByLabel("Password", { exact: true }).fill("incorrect");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Email or password is incorrect" }),
  ).toBeVisible();
});
test("login cannot submit credentials before hydration", async ({
  browser,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("http://localhost:3100/login");
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeDisabled();
  await expect(page.locator("form")).toHaveAttribute("method", "post");
  await context.close();
});
