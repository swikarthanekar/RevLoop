/**
 * Single source of truth for E2E addresses.
 *
 * Ports are deliberately offset from the usual dev ports so an E2E run never
 * collides with a developer's own `next dev` / `uvicorn` session.
 */

export const API_PORT = Number(process.env.E2E_API_PORT ?? 8100);
export const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 3100);
export const PROVIDER_STUB_PORT = Number(process.env.E2E_PROVIDER_STUB_PORT ?? 8200);

export const API_BASE_URL = `http://127.0.0.1:${API_PORT}`;
export const WEB_BASE_URL = `http://localhost:${WEB_PORT}`;

/** Local deterministic Razorpay-compatible stub the real client talks to. */
export const PROVIDER_STUB_BASE_URL = `http://127.0.0.1:${PROVIDER_STUB_PORT}`;

/**
 * Obviously fake but syntactically valid Razorpay test credentials.
 *
 * They exist only so the production client passes its normal configuration
 * checks against the local stub. They are never `NEXT_PUBLIC`, never logged, and
 * are not real credentials.
 */
export const PROVIDER_TEST_KEY_ID = "rzp_test_e2elocalstub";
export const PROVIDER_TEST_KEY_SECRET = "e2elocalstubsecret";

/** Deterministic test-only webhook secret; matches the backend E2E env. */
export const WEBHOOK_SECRET =
  process.env.E2E_RAZORPAY_WEBHOOK_SECRET ?? "dev-razorpay-webhook-secret";

/** Demo customer seeded by `seed_demo_database`, correlated via payment notes. */
export const DEMO_CUSTOMER_EXTERNAL_ID = "demo-customer-0001";

/**
 * The deterministic fixture amount, in minor units (₹40,000).
 *
 * Two properties matter and are both asserted by the specs:
 *  - it is larger than every seeded case, so the "Minimum amount at risk"
 *    filter isolates exactly one row;
 *  - it is above the demo auto-action limit (₹10,000), so the policy engine
 *    deterministically requires approval via AMOUNT_ABOVE_AUTO_ACTION_LIMIT.
 */
export const FIXTURE_AMOUNT_MINOR = 4_000_000;

export const FIXTURE_CURRENCY = "INR";
