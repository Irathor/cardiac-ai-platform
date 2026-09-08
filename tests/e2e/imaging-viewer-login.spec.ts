import { expect, test } from "@playwright/test";

/**
 * A real login against the real backend/Postgres (seeded by
 * backend/app/scripts/seed_demo.py — see the Makefile's `make seed`). If
 * this fails, either the stack isn't running or the demo seed hasn't been
 * applied; it is not mocked like frontend/tests/ImagingViewerPage.test.tsx.
 */
test("logging in with the seeded demo doctor reveals the study/series controls", async ({ page }) => {
  await page.goto("/viewer");

  // The form is pre-filled with the demo doctor's credentials by default.
  await expect(page.getByLabel("Email")).toHaveValue("doctor@demo.cardiacai-test.dev");
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page.getByLabel("Study ID")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("button", { name: "Load series" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run AI analysis" })).toBeVisible();
});

test("logging in with a wrong password shows an error and stays on the login form", async ({ page }) => {
  await page.goto("/viewer");

  await page.getByLabel("Password").fill("definitely-not-the-right-password");
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page.getByText(/login failed/i)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByLabel("Email")).toBeVisible();
});
