import { expect, test } from "@playwright/test";

test("dashboard shows the disclaimer, the title, and a live backend status", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByText("Research prototype only. Not validated for clinical diagnosis or treatment decisions."),
  ).toBeVisible();
  await expect(page.getByText("CardiacAI Research Platform")).toBeVisible();

  // Hits the real backend (see docker-compose.yml) — not mocked, unlike the
  // frontend's own unit tests.
  await expect(page.getByText("online")).toBeVisible({ timeout: 10_000 });
});

test("navigating to the imaging viewer shows its login form", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Imaging viewer" }).click();

  await expect(page).toHaveURL(/\/viewer$/);
  await expect(page.getByRole("heading", { name: "Imaging viewer" })).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
});
