/**
 * Deterministic local Razorpay-compatible stub for E2E.
 *
 * It implements only the Payment Link operations the tested fixture reaches, so
 * the real production RazorpayClient performs a genuine HTTP request without any
 * live Razorpay dependency. It is not a Razorpay emulator.
 *
 * The `/__e2e__/*` routes exist solely so the browser test can assert what the
 * backend actually sent to the provider.
 */

import { createHash } from "node:crypto";
import { createServer } from "node:http";

const PORT = Number(process.env.E2E_PROVIDER_STUB_PORT ?? 8200);

/** Every provider request the backend made, in order. */
const received = [];
/** Payment links created, keyed by reference_id, for reference lookups. */
const linksByReference = new Map();

/** Razorpay-style identifier derived from the reference so runs are repeatable. */
function paymentLinkId(referenceId) {
  const digest = createHash("sha256").update(referenceId).digest("hex");
  return `plink_${digest.slice(0, 14)}`;
}

function send(response, status, body) {
  const payload = JSON.stringify(body);
  response.writeHead(status, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(payload),
  });
  response.end(payload);
}

function createPaymentLink(body) {
  const referenceId = body.reference_id;
  const link = {
    id: paymentLinkId(referenceId),
    entity: "payment_link",
    reference_id: referenceId,
    amount: body.amount,
    currency: body.currency,
    status: "created",
    accept_partial: body.accept_partial === true,
    amount_paid: 0,
    description: body.description ?? null,
    short_url: `http://127.0.0.1:${PORT}/l/${paymentLinkId(referenceId)}`,
    notes: body.notes ?? {},
    created_at: Math.floor(Date.now() / 1000),
  };
  linksByReference.set(referenceId, link);
  return link;
}

const server = createServer((request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${PORT}`);
  const chunks = [];
  request.on("data", (chunk) => chunks.push(chunk));
  request.on("end", () => {
    const raw = Buffer.concat(chunks).toString("utf-8");

    if (url.pathname === "/__e2e__/health") {
      return send(response, 200, { status: "ok" });
    }
    if (url.pathname === "/__e2e__/requests" && request.method === "GET") {
      return send(response, 200, { requests: received });
    }
    if (url.pathname === "/__e2e__/reset" && request.method === "POST") {
      received.length = 0;
      linksByReference.clear();
      return send(response, 200, { status: "reset" });
    }

    // The real client authenticates with HTTP Basic. Presence is verified; the
    // value is never recorded or logged.
    const authenticated = (request.headers.authorization ?? "").startsWith("Basic ");

    let body = null;
    if (raw) {
      try {
        body = JSON.parse(raw);
      } catch {
        body = null;
      }
    }

    received.push({
      method: request.method,
      path: url.pathname,
      query: Object.fromEntries(url.searchParams.entries()),
      authenticated,
      body,
    });

    if (!authenticated) {
      return send(response, 401, { error: { description: "Authentication required." } });
    }

    if (request.method === "POST" && url.pathname === "/v1/payment_links") {
      if (!body || typeof body.reference_id !== "string" || !Number.isInteger(body.amount)) {
        return send(response, 400, { error: { description: "Invalid payment link request." } });
      }
      return send(response, 200, createPaymentLink(body));
    }

    if (request.method === "GET" && url.pathname === "/v1/payment_links/") {
      const link = linksByReference.get(url.searchParams.get("reference_id"));
      return send(response, 200, { items: link ? [link] : [], count: link ? 1 : 0 });
    }

    // Analysis reads provider downtime signals. "No active downtime" is the
    // deterministic answer for these fixtures.
    if (request.method === "GET" && url.pathname === "/v1/payments/downtimes") {
      return send(response, 200, {
        entity: "collection",
        payment_downtime: { entity: "collection", count: 0, items: [] },
      });
    }

    return send(response, 404, { error: { description: "Not found." } });
  });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[provider-stub] listening on http://127.0.0.1:${PORT}`);
});
