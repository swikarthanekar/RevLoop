# RecoverIQ — Razorpay Integration Specification

**Status:** P0 payment-provider contract  
**Mode:** Razorpay Test Mode for hackathon  
**Last architecture verification:** 2026-08-30 against official Razorpay documentation.

## 1. Scope

### Genuinely integrated in P0
1. Webhook signature verification.
2. Webhook event deduplication using `x-razorpay-event-id`.
3. Failed payment ingestion (`payment.failed`).
4. Successful payment evidence (`payment.captured`; Payment Link `payment_link.paid` where used).
5. Subscription events: `subscription.pending`, `subscription.charged`, `subscription.halted`.
6. Fetch payment by ID for reconciliation where needed: `GET /v1/payments/:id`.
7. Standard Payment Link creation for a small number of live demo cases: `POST /v1/payment_links`.
8. Standard Payment Link fetch for unknown/reconciliation flow: `GET /v1/payment_links/:id`.
9. Payment downtime list/read: `GET /v1/payments/downtimes` and, where needed, `GET /v1/payments/downtimes/:id`.

### Simulated in P0
- bulk recovery outcomes for synthetic batch evaluation;
- delivery of email/WhatsApp unless optional email adapter is added later;
- direct autonomous same-method debit for one-time failures;
- any unsupported/manual provider operation not available safely through documented API;
- production settlement of real money.

### Explicitly not integrated
- Stripe or other payment provider;
- real customer production accounts;
- live-mode money movement;
- refunds/disputes.

## 2. Client architecture

Expected modules:

```text
apps/api/app/integrations/razorpay/
  client.py
  schemas.py
  errors.py
  webhooks.py
  payments.py
  payment_links.py
  subscriptions.py
  downtime.py
```

Use a thin HTTP/provider adapter. The adapter returns internal DTOs and typed exceptions; it does not decide recovery policy.

## 3. Authentication for API calls

Razorpay API client uses server-side credentials:

```text
RAZORPAY_KEY_ID
RAZORPAY_KEY_SECRET
```

Never send the key secret to the browser.

Use HTTPS and bounded timeouts.

## 4. Webhook signature verification

Razorpay sends a signature in:

```http
X-Razorpay-Signature
```

Official signature algorithm:

```text
HMAC-SHA256
key     = webhook secret
message = raw webhook request body
```

Implementation rule:

```python
expected = hmac.new(
    webhook_secret.encode(),
    raw_body,
    hashlib.sha256,
).hexdigest()

if not hmac.compare_digest(expected, received_signature):
    raise InvalidWebhookSignature()
```

You may use the official SDK verifier if dependency choice is justified, but tests must still cover raw-body behavior.

**Never parse/re-serialize JSON before signature verification.** The exact raw bytes are part of the signature.

## 5. Webhook idempotency

Razorpay may deliver the same event multiple times. Use:

```http
x-razorpay-event-id
```

as provider event ID.

Database constraint:

```text
UNIQUE(provider, provider_event_id)
```

Processing:

```text
verify signature
→ read event id
→ insert webhook event RECEIVED
→ uniqueness conflict?
   yes → return 204, no domain reprocessing
   no  → process
```

Do not use payload hash as the primary event identity when the provider event ID is available.

## 6. Webhook ordering

Do not assume delivery order.

For each relevant provider entity:
- persist provider event time;
- keep `last_provider_event_at`;
- use status precedence and success evidence;
- fetch current provider entity when local evidence is ambiguous.

Examples:
- `payment.captured` may arrive before/around older authorization-related events;
- a stale `payment.failed` cannot downgrade a payment already verified `captured`;
- old `subscription.pending` must not reopen a case already resolved by a later `subscription.charged` for the same recovery episode.

## 7. Webhook events to subscribe to

### Payments
P0:
- `payment.failed`
- `payment.captured`

Optional informational:
- `order.paid` if the demo uses Orders and it helps correlate outcome. Do not double-count `order.paid` and `payment.captured` as two recoveries.

### Payment Links
P0 when Payment Links are used:
- `payment_link.paid`
- optionally `payment_link.cancelled`
- optionally `payment_link.expired`

Do not enable partial payments in the P0 recovery link unless product logic is extended to support partial recovered amounts. Recommended P0: `accept_partial=false`.

### Subscriptions
P0:
- `subscription.pending`
- `subscription.charged`
- `subscription.halted`

Optional:
- activation/status events only if needed for demo synchronization.

## 8. Failed payment ingestion

`payment.failed` contains a payment snapshot and may include:
- payment ID;
- amount/currency;
- method;
- status;
- order ID;
- `error_code`;
- `error_description`;
- `error_reason`;
- `error_source`;
- `error_step`.

Handler:

```text
verified payment.failed
→ upsert Transaction
→ compare provider event time/current status
→ if payment not already captured
→ create/get RecoveryCase using stable source_event_key
→ audit CASE_CREATED or DUPLICATE/STALE_EVENT
→ schedule analysis; no LLM in webhook request
```

## 9. Successful payment verification

### 9.1 Preferred webhook evidence

For ordinary payment recovery:

```text
payment.captured
```

For a created Payment Link:

```text
payment_link.paid
```

The Payment Link paid payload includes Payment Link, order and payment context. Link the event back to `RecoveryAction` using the provider Payment Link ID/reference stored on the action.

### 9.2 Reconciliation fetch

If webhook is missing/ambiguous and a provider payment ID is known:

```http
GET /v1/payments/:id
```

Treat status `captured` as verified payment success for P0.

### 9.3 Outcome creation

Before marking `RECOVERED` verify:
- payment belongs to correct organization/provider account context;
- amount/currency are compatible with the recovery case;
- provider/payment link reference maps to case or source transaction safely;
- outcome does not already exist.

Then atomically:
- insert `RecoveryOutcome`;
- transition case `RECOVERED`;
- cancel non-executed scheduled recovery actions;
- audit.

## 10. Payment Links

### Create Standard Payment Link

```http
POST /v1/payment_links
```

P0 request fields:

```json
{
  "amount": 499900,
  "currency": "INR",
  "accept_partial": false,
  "reference_id": "rq_<stable-short-action-ref>",
  "description": "RecoverIQ payment recovery",
  "customer": {
    "name": "Synthetic Demo Customer"
  },
  "notify": {
    "sms": false,
    "email": false
  },
  "reminder_enable": false,
  "notes": {
    "recoveriq_case": "short-safe-id"
  }
}
```

Use only fields supported by the API version/SDK actually installed. Do not include null/unverified fields just because examples contain them.

### Provider constraints relevant to P0
- amount is in smallest currency unit;
- `reference_id` must be unique per Payment Link and has a documented max length;
- test mode currently permits only a limited number of Payment Links per business (official docs state 30), so do not generate links for synthetic batch evaluation.

### Local idempotency
Before create:
1. create `RecoveryAction` with unique local idempotency key;
2. derive unique provider `reference_id`;
3. commit action intent;
4. call create.

If request result is unknown:
- mark action `UNKNOWN`;
- do not immediately create another link;
- reconcile using known provider ID if received, local reference/audit data, or operator path.

### Fetch Payment Link

```http
GET /v1/payment_links/:id
```

Use for status reconciliation when provider reference is known.

## 11. Subscription behavior

Razorpay subscription semantics are important to the product.

### `subscription.pending`
Means an auto-charge was unsuccessful. Razorpay may continue automatic retry behavior while pending depending on payment method/product configuration.

RecoverIQ behavior:
- upsert subscription state;
- create/update recovery case for the current failure episode;
- classify `MANDATE_OR_RECURRING_FAILURE` unless stronger payment failure evidence exists;
- **do not default to an immediate competing retry**;
- candidates favor `WAIT`, alternate method/card update, bounded message, STOP.

### `subscription.charged`
Successful charge evidence.

If related recovery case is non-terminal:
- create verified outcome;
- mark case `RECOVERED`;
- stop/cancel pending RecoverIQ interventions.

### `subscription.halted`
Provider retries are exhausted according to Razorpay state.

RecoverIQ candidates may become:
- request alternate payment method;
- Payment Link where product flow makes sense;
- manual escalation;
- STOP.

The exact recovery path should never claim Razorpay will automatically collect historical halted invoices unless current docs/product behavior supports it.

### Test mode
Use Razorpay's documented subscription testing controls to demonstrate successful and failed charge paths where available in the merchant dashboard/test workflow.

## 12. Payment Downtime

### Fetch all

```http
GET /v1/payments/downtimes
```

The list endpoint does not require P0 pagination/filtering logic; map the returned collection into internal downtime DTOs.

### Fetch by ID

```http
GET /v1/payments/downtimes/:id
```

Use when a known downtime ID needs reconciliation.

### Internal normalized DTO

```python
class PaymentDowntime(BaseModel):
    id: str
    method: str
    status: str
    severity: str | None
    scheduled: bool
    begin_at: datetime | None
    end_at: datetime | None
    instrument: dict[str, str]
```

### Matching
Match active downtime to failed payment using:
- method;
- instrument details if available (issuer/network/card type);
- time window;
- status.

Do not mark every UPI/card failure as downtime simply because one unrelated instrument is degraded.

### Failure handling
Downtime endpoint timeout/error:

```text
downtime_context = UNKNOWN
```

Analysis continues with reduced evidence/confidence.

## 13. Provider error mapping

Integration layer maps HTTP failures into typed errors:

```text
RazorpayAuthenticationError
RazorpayValidationError
RazorpayRateLimitError
RazorpayTransientError
RazorpayTimeoutUnknownResult
RazorpayNotFoundError
```

Do not leak Razorpay key secret or full raw sensitive response in UI errors.

## 14. Timeouts and retries

Suggested starting values:
- connect: 3s;
- read: 8s;
- total bounded by route budget.

GET/fetch calls may receive small bounded technical retry on transient failures.

POST Payment Link creation:
- no blind automatic repeat after unknown timeout;
- reconcile first.

## 15. Test-mode demo workflow

### Flow A — payment failure case
1. Seed/create demo transaction context.
2. Receive or replay a **signature-valid test fixture only in test harness**; for live demo prefer actual Razorpay test-mode event.
3. Case appears.
4. Analyze.
5. Select/create Payment Link or alternate-method recovery action.
6. Open generated Razorpay test link.
7. Complete test payment as success.
8. `payment_link.paid`/payment success webhook resolves case.
9. Dashboard recovered revenue increases.

### Flow B — subscription
1. Prepare a Razorpay test subscription.
2. Simulate/test a failed subsequent charge using documented test flow.
3. Receive `subscription.pending`.
4. RecoverIQ recommends WAIT/alternate method depending context.
5. Demonstrate successful test charge/card-change path if reliable.
6. `subscription.charged` resolves case.

If live subscription setup is too brittle during judging, keep the subscription event path demonstrable with recorded/verified test fixture in the automated integration suite and use Payment Link as the live demo money-recovery path.

## 16. Webhook testing requirements

Must include tests for:
- valid signature over raw bytes;
- changed whitespace/body invalidates mismatched signature fixture as expected;
- invalid signature rejected;
- duplicate event ID returns idempotent success;
- out-of-order captured then failed does not regress;
- `subscription.charged` resolves a pending case;
- older `subscription.pending` after charged is ignored;
- Payment Link paid maps to correct action/case;
- unknown event type recorded/ignored safely.

## 17. Official behavior assumptions to re-check before final demo

Because provider APIs can evolve, one day before submission verify in official Razorpay docs/dashboard:
- enabled webhook event names;
- Payment Link request fields and test-mode quota;
- subscription test controls;
- downtime API availability with current test key;
- webhook endpoint accessibility from deployed backend.

Do not redesign RecoverIQ based on minor provider changes; update only adapter details.
