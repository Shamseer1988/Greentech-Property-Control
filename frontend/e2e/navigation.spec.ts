import { expect, test } from "@playwright/test";

const ADMIN_USER = process.env.E2E_USER || "admin";
const ADMIN_PASS = process.env.E2E_PASS || "ChangeMe123!";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel(/username or email/i).fill(ADMIN_USER);
  await page.getByLabel(/^password$/i).fill(ADMIN_PASS);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
}

test.describe("navigation + key list pages", () => {
  test("dashboard → properties → landlords", async ({ page }) => {
    await signIn(page);

    // Each list renders its page heading and either a table or an
    // empty state — both are a pass; we're checking the route mounts.
    await page.goto("/properties");
    await expect(page.getByRole("heading", { name: /properties/i, level: 1 })).toBeVisible();

    await page.goto("/landlords");
    await expect(page.getByRole("heading", { name: /landlords/i, level: 1 })).toBeVisible();
  });

  test("global search ⌘K typeahead reaches dashboard action", async ({ page }) => {
    await signIn(page);
    await page.keyboard.press("ControlOrMeta+KeyK");
    const search = page.getByRole("searchbox", { name: /search/i });
    await search.focus();
    await search.fill("dashboard");
    // The dashboard action ("Go to dashboard") should be visible
    // even before the server search round-trips.
    await expect(page.locator("text=/go to dashboard/i")).toBeVisible({ timeout: 3_000 });
  });
});
