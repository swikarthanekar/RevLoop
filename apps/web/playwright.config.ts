import { defineConfig, devices } from "@playwright/test";

import {
  API_BASE_URL,
  API_PORT,
  PROVIDER_STUB_BASE_URL,
  PROVIDER_STUB_PORT,
  PROVIDER_TEST_KEY_ID,
  PROVIDER_TEST_KEY_SECRET,
  WEB_BASE_URL,
  WEB_PORT,
} from "./e2e/fixtures/env";

const DATABASE_URL =
  process.env.REVLOOP_TEST_DATABASE_URL ??
  "postgresql+psycopg://revloop:revloop@localhost:5433/revloop_test";

/** Canonical demo tenant identities, mirroring app/demo/constants.py. */
const DEV_AUTH_USER_ID = "bc9f0349-0af8-557e-9557-4bdaadda544d";
const DEV_AUTH_ORGANIZATION_ID = "82757dbc-e0d0-5285-8f26-7a9ab9837a24";

const backendEnv = {
  DATABASE_URL,
  APP_ENV: "test",
  DEMO_MODE: "true",
  DEV_AUTH_USER_ID,
  DEV_AUTH_ORGANIZATION_ID,
  PUBLIC_APP_BASE_URL: WEB_BASE_URL,
  RAZORPAY_WEBHOOK_SECRET: "dev-razorpay-webhook-secret",
  // Fake-but-valid provider credentials plus a local base URL, so the real
  // RazorpayClient is constructed and sends a genuine Payment Link POST to the
  // deterministic stub instead of live Razorpay. The base URL override is only
  // accepted because APP_ENV is not production.
  RAZORPAY_KEY_ID: PROVIDER_TEST_KEY_ID,
  RAZORPAY_KEY_SECRET: PROVIDER_TEST_KEY_SECRET,
  RAZORPAY_API_BASE_URL: PROVIDER_STUB_BASE_URL,
  // GEMINI_API_KEY is deliberately empty, which disables the LLM path.
  GEMINI_API_KEY: "",
};

export default defineConfig({
  testDir: "./e2e",
  // Every spec mutates the shared demo database and resets it in beforeEach, so
  // the suite runs serially. See PROMPT_25 report section 3.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  // A flaky test that only passes on retry is not acceptable for this milestone.
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? "line" : [["list"]],
  use: {
    baseURL: WEB_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // The sidebar navigation is `hidden md:flex`, so a desktop viewport is
    // required for the real navigation controls to exist.
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `node e2e/provider-stub/server.mjs`,
      cwd: ".",
      url: `${PROVIDER_STUB_BASE_URL}/__e2e__/health`,
      env: { E2E_PROVIDER_STUB_PORT: String(PROVIDER_STUB_PORT) },
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command:
        "bash -c 'source .venv/bin/activate" +
        " && alembic upgrade head" +
        ' && python -c "from app.demo.seed import seed_demo_database; seed_demo_database(reset=True)"' +
        ` && python -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}'`,
      cwd: "../api",
      url: `${API_BASE_URL}/health`,
      env: backendEnv,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: `npm run build && npm run start -- --port ${WEB_PORT}`,
      cwd: ".",
      url: WEB_BASE_URL,
      env: {
        // NEXT_PUBLIC_* values are inlined at build time, so they must be set
        // for the build step as well as the server.
        NEXT_PUBLIC_API_BASE_URL: API_BASE_URL,
        NEXT_PUBLIC_DEV_AUTH_TOKEN: "dev-admin",
      },
      reuseExistingServer: !process.env.CI,
      timeout: 300_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
