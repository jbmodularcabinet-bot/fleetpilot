import { expect, type Page } from "@playwright/test";

/** Verify inherited v1 styles on the real rendered delivery workflow. */
export async function expectLockedV1(
  page: Page,
  own: boolean,
  panel = "Delivery evidence",
) {
  await expect(
    page.getByRole("heading", { name: panel, exact: true }),
  ).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const design = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    return {
      font: getComputedStyle(document.body).fontFamily,
      interLoaded: document.fonts.check('16px "Inter"'),
      colors: Object.fromEntries(
        ["navy", "slate", "mint", "blue", "amber", "red", "cloud"].map(
          (token) => [
            token,
            root.getPropertyValue(`--${token}`).trim().toLowerCase(),
          ],
        ),
      ),
    };
  });
  expect(design.font).toContain("Inter");
  expect(design.interLoaded).toBe(true);
  expect(design.colors).toEqual({
    navy: "#08111f",
    slate: "#162235",
    mint: "#2be0a7",
    blue: "#3b82f6",
    amber: "#f5a524",
    red: "#f04444",
    cloud: "#f6f8fa",
  });
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(246, 248, 250)",
  );
  await expect(
    page
      .locator(".master-card")
      .filter({ has: page.getByRole("heading", { name: panel, exact: true }) }),
  ).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(
    page
      .locator(".master-card")
      .filter({ has: page.getByRole("heading", { name: panel, exact: true }) }),
  ).toHaveCSS("border-radius", "12px");
  if (own) {
    const nav = page.getByRole("navigation", { name: "Driver navigation" });
    await expect(nav).toHaveCSS("background-color", "rgb(255, 255, 255)");
    await expect(nav.getByRole("link")).toHaveText([
      "Home",
      "Trips",
      "Profile",
    ]);
    await expect(nav.getByRole("button", { name: "Expenses" })).toBeDisabled();
    await expect(nav.getByRole("button", { name: "Alerts" })).toBeDisabled();
  } else {
    await expect(page.locator(".sidebar")).toHaveCSS(
      "background-color",
      "rgb(8, 17, 31)",
    );
    await expect(page.locator(".sidebar .brand")).toHaveCSS(
      "background-image",
      /brand-reference\.png/,
    );
  }
}
