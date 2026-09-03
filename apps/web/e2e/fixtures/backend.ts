/**
 * Test-side backend helpers.
 *
 * These exist only for deterministic prerequisite setup, for posting genuinely
 * signed provider webhooks, and for reading public backend state where the
 * browser is not the assertion target. No application API response is ever
 * faked or intercepted: every product interaction in the specs goes through the
 * real UI against the real backend.
 */

import { createHmac, randomBytes } from "node:crypto";

import type { APIRequestContext } from "@playwright/test";
import { expect } from "@playwright/test";

import {
  API_BASE_URL,
  DEMO_CUSTOMER_EXTERNAL_ID,
  FIXTURE_AMOUNT_MINOR,
  FIXTURE_CURRENCY,
  PROVIDER_STUB_BASE_URL,
  WEBHOOK_SECRET,
} from "./env";

export const ADMIN_HEADERS = { Authorization: "Bearer dev-admin" };

export function uniqueSuffix(): string {
  return randomBytes(6).toString("hex");
}

/** Seconds since epoch for a failure that just happened. */
function recentEpoch(offsetSeconds = 3600): number {
  return Math.floor(Date.now() / 1000) - offsetSeconds;
}

/**
 * Sign and post a webhook through the real `/api/v1/webhooks/razorpay` route.
 *
 * The HMAC is computed over the exact bytes that are sent, so the production
 * signature check runs unmodified. Neither the secret nor the signature is ever
 * logged.
 */
export async function postSignedWebhook(
  request: APIRequestContext,
  payload: unknown,
  eventId: string,
): Promise<number> {
  const rawBody = Buffer.from(JSON.stringify(payload), "utf-8");
  const signature = createHmac("sha256", WEBHOOK_SECRET).update(rawBody).digest("hex");

  const response = await request.post(`${API_BASE_URL}/api/v1/webhooks/razorpay`, {
    data: rawBody,
    headers: {
      "Content-Type": "application/json",
      "X-Razorpay-Signature": signature,
      "x-razorpay-event-id": eventId,
    },
  });
  return response.status();
}

export function failurePayload(paymentId: string, amountMinor = FIXTURE_AMOUNT_MINOR) {
  const occurredAt = recentEpoch();
  return {
    event: "payment.failed",
    created_at: occurredAt,
    payload: {
      payment: {
        entity: {
          id: paymentId,
          entity: "payment",
          amount: amountMinor,
          currency: FIXTURE_CURRENCY,
          status: "failed",
          method: "upi",
          created_at: occurredAt,
          notes: { revloop_customer: DEMO_CUSTOMER_EXTERNAL_ID },
          error_code: "BAD_REQUEST_ERROR",
          error_reason: "payment_failed",
        },
      },
    },
  };
}

/**
 * A success envelope for a Payment Link the provider actually created.
 *
 * `providerLinkId` is the identifier returned by the provider during creation,
 * so the create and the success webhook describe one coherent lifecycle rather
 * than two unrelated references that happen to match.
 */
export function paymentLinkPaidPayload({
  referenceId,
  providerLinkId,
  paymentId,
  amountMinor = FIXTURE_AMOUNT_MINOR,
}: {
  referenceId: string;
  providerLinkId: string;
  paymentId: string;
  amountMinor?: number;
}) {
  const occurredAt = recentEpoch(60);
  return {
    event: "payment_link.paid",
    created_at: occurredAt,
    payload: {
      payment_link: {
        entity: {
          id: providerLinkId,
          entity: "payment_link",
          reference_id: referenceId,
          amount: amountMinor,
          currency: FIXTURE_CURRENCY,
          status: "paid",
        },
      },
      payment: {
        entity: {
          id: paymentId,
          entity: "payment",
          amount: amountMinor,
          currency: FIXTURE_CURRENCY,
          status: "captured",
          method: "upi",
          created_at: occurredAt,
          notes: { revloop_customer: DEMO_CUSTOMER_EXTERNAL_ID },
        },
      },
    },
  };
}

/** One request the backend's real RazorpayClient sent to the local stub. */
export interface ProviderRequest {
  method: string;
  path: string;
  query: Record<string, string>;
  authenticated: boolean;
  body: Record<string, unknown> | null;
}

export async function resetProviderStub(request: APIRequestContext): Promise<void> {
  const response = await request.post(`${PROVIDER_STUB_BASE_URL}/__e2e__/reset`);
  expect(response.status(), "provider stub is not reachable").toBe(200);
}

export async function providerRequests(
  request: APIRequestContext,
): Promise<ProviderRequest[]> {
  const response = await request.get(`${PROVIDER_STUB_BASE_URL}/__e2e__/requests`);
  expect(response.status()).toBe(200);
  return (await response.json()).requests as ProviderRequest[];
}

/** Payment Link create calls the backend made, in order. */
export async function paymentLinkCreates(
  request: APIRequestContext,
): Promise<ProviderRequest[]> {
  const all = await providerRequests(request);
  return all.filter((entry) => entry.method === "POST" && entry.path === "/v1/payment_links");
}

/** Restore exact canonical demo state so each test starts identically. */
export async function resetDemoState(request: APIRequestContext): Promise<void> {
  const response = await request.post(`${API_BASE_URL}/api/v1/demo/reset`, {
    headers: ADMIN_HEADERS,
    data: {},
  });
  expect(
    response.status(),
    `demo reset failed with ${response.status()}`,
  ).toBe(200);
}

/**
 * Create the deterministic recovery case through the real webhook boundary and
 * return its id. The case is never inserted directly.
 */
export async function createFixtureCase(
  request: APIRequestContext,
  suffix: string,
): Promise<{ caseId: string; paymentId: string; customerName: string }> {
  const paymentId = `pay_e2e_${suffix}`;
  const status = await postSignedWebhook(
    request,
    failurePayload(paymentId),
    `evt_e2e_fail_${suffix}`,
  );
  expect(status, "failure webhook was not accepted").toBe(204);

  const listed = await request.get(
    `${API_BASE_URL}/api/v1/recovery-cases?min_amount_minor=${FIXTURE_AMOUNT_MINOR}&limit=100`,
    { headers: ADMIN_HEADERS },
  );
  expect(listed.status()).toBe(200);
  const body = await listed.json();
  expect(
    body.items.length,
    `expected exactly one fixture case at ${FIXTURE_AMOUNT_MINOR} minor, got ${body.items.length}`,
  ).toBe(1);

  return {
    caseId: body.items[0].id,
    paymentId,
    customerName: body.items[0].customer.display_name,
  };
}

export async function getCase(request: APIRequestContext, caseId: string) {
  const response = await request.get(`${API_BASE_URL}/api/v1/recovery-cases/${caseId}`, {
    headers: ADMIN_HEADERS,
  });
  expect(response.status()).toBe(200);
  return response.json();
}

export async function getDashboardRecoveredMinor(
  request: APIRequestContext,
): Promise<number> {
  const response = await request.get(`${API_BASE_URL}/api/v1/dashboard/summary`, {
    headers: ADMIN_HEADERS,
  });
  expect(response.status()).toBe(200);
  const body = await response.json();
  return Number(body.revenue_recovered_minor);
}

/**
 * Parse a rendered INR amount back to minor units using integer-safe logic.
 *
 * `formatMoneyMinor` renders minor units with `en-IN` currency formatting, so
 * "₹40,000.00" must round-trip to 4000000 with no floating point involved.
 */
export function parseInrMinor(displayed: string): number {
  const trimmed = displayed.trim();
  const negative = trimmed.startsWith("-");
  const digits = trimmed.replace(/[^0-9.]/g, "");
  const [major, fraction = ""] = digits.split(".");
  const paise = `${fraction}00`.slice(0, 2);
  const minor = Number(major) * 100 + Number(paise);
  return negative ? -minor : minor;
}
