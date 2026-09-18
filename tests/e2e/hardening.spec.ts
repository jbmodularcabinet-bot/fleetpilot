import { test, expect } from "@playwright/test";

test("locked owner screens and nonce headers survive hardening", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email address").fill("carlo@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const nonces = new Set<string>();
  for (const path of [
    "/dashboard",
    "/customers",
    "/fleet/vehicles",
    "/fleet/drivers",
    "/dispatch",
  ]) {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    const csp = response!.headers()["content-security-policy"];
    expect(csp).toContain("'strict-dynamic'");
    const scriptPolicy = csp
      .split(";")
      .find((value) => value.includes("script-src"))!;
    expect(scriptPolicy).not.toContain("'unsafe-inline'");
    if (process.env.FLEETPILOT_PRODUCTION_SMOKE === "1") {
      expect(scriptPolicy).not.toContain("'unsafe-eval'");
    }
    const nonce = /'nonce-([^']+)'/.exec(csp)![1];
    expect(nonces.has(nonce)).toBe(false);
    nonces.add(nonce);
    await expect(page.locator(".sidebar")).toHaveCSS(
      "background-color",
      "rgb(8, 17, 31)",
    );
    await expect(page.locator(".sidebar .brand")).toHaveCSS(
      "background-image",
      /brand-reference\.png/,
    );
    await expect(page.locator("body")).toHaveCSS(
      "background-color",
      "rgb(246, 248, 250)",
    );
    await expect(page.locator("body")).toHaveCSS("font-family", /Inter/);
    await expect(
      page.getByRole("navigation", { name: "Main navigation" }),
    ).toBeVisible();
    await expect(page.locator("h1")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  expect(errors).toEqual([]);
});

test("locked driver home and assigned trips remain mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await page.getByLabel("Email address").fill("juan@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.DEMO_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/driver$/);
  await expect(page.locator(".driver-brand .brand")).toHaveCSS(
    "background-image",
    /brand-reference\.png/,
  );
  for (const path of ["/driver", "/driver/trips"]) {
    await page.goto(path);
    await expect(
      page.getByRole("navigation", { name: "Driver navigation" }),
    ).toHaveCSS("background-color", "rgb(255, 255, 255)");
    await expect(page.locator("body")).toHaveCSS("font-family", /Inter/);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});
