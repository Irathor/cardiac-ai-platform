import { defineConfig, devices } from "@playwright/test";

/**
 * Runs against the full docker-compose stack (see README.md's Quickstart) —
 * `docker compose up` must already be running before `npm test` here.
 * These are cross-cutting checks that exercise the real frontend against the
 * real backend/Postgres/MinIO, not a substitute for the frontend's own
 * mocked unit tests (see frontend/tests) or the backend's own API tests
 * (see backend/tests).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
