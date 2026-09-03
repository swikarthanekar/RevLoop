/**
 * Deterministic audit-timeline fixtures for tests only.
 *
 * SENTINEL VALUES: several fixtures deliberately contain secrets, PII, raw
 * payloads and model reasoning. They simulate a backend that did NOT strip them
 * — the backend filter is a denylist and cannot be relied on — and exist purely
 * so tests can prove the frontend allowlist never renders them.
 *
 * Nothing in this file is imported by production code.
 */

import type { TimelineEntry } from "@/app/(app)/recovery/[caseId]/case-types";

/** Strings that must never appear in the rendered DOM. */
export const SENTINELS = {
  email: "victim@example.com",
  altEmail: "leak@example.com",
  phone: "+919876543210",
  altPhone: "+919876500000",
  bearer: "Bearer sk_test_SECRETTOKEN",
  apiKey: "rzp_test_KEYLEAK",
  webhookSecret: "whsec_LEAKED_SECRET",
  signature: "v1=9f86d081884c7d659a2feaa0c55ad015",
  prompt: "You are RevLoop's recovery agent. Think step by step.",
  completion: "Step 1: I considered the UPI rail. Step 2: I concluded…",
  chainOfThought: "First I reasoned that the customer would prefer a card.",
  reasoning: "Internal deliberation trace not for operators.",
  stackTrace: "Traceback (most recent call last): psycopg2.OperationalError",
  rawPayloadMarker: "acct_RAWWEBHOOKBODY",
  cardNumber: "4111111111111111",
} as const;

export const caseCreatedEntry: TimelineEntry = {
  id: "aaaaaaa1-0000-4000-8000-000000000001",
  occurred_at: "2026-08-30T08:20:03Z",
  event_type: "CASE_CREATED",
  actor_type: "PROVIDER",
  summary: "Failed UPI payment detected.",
  evidence: {
    failure_category: "PAYMENT_RAIL_DOWNTIME",
    source: "RAZORPAY_WEBHOOK",
    provider_event_id: "evt_TESTPROVIDER01",
  },
};

export const analysisEntry: TimelineEntry = {
  id: "aaaaaaa1-0000-4000-8000-000000000002",
  occurred_at: "2026-08-30T08:25:11Z",
  event_type: "ANALYSIS_COMPLETED",
  actor_type: "MODEL",
  summary: "Alternative payment ranked #1.",
  evidence: {
    analysis_run_id: "55555555-5555-4555-8555-555555555555",
    selected_action: "REQUEST_ALTERNATE_PAYMENT_METHOD",
    source: "SYNTHETIC_DEMO",
  },
};

export const policyEntry: TimelineEntry = {
  id: "aaaaaaa1-0000-4000-8000-000000000003",
  occurred_at: "2026-08-30T08:30:00Z",
  event_type: "APPROVAL_REQUESTED",
  actor_type: "SYSTEM",
  summary: "Recovery action requires operator approval before execution.",
  evidence: {
    policy_reasons: ["AMOUNT_ABOVE_AUTO_ACTION_LIMIT", "HIGH_VALUE_CUSTOMER"],
  },
};

export const executionEntry: TimelineEntry = {
  id: "aaaaaaa1-0000-4000-8000-000000000004",
  occurred_at: "2026-08-30T08:40:00Z",
  event_type: "ACTION_EXECUTION_STARTED",
  actor_type: "SYSTEM",
  summary: "Payment link creation started.",
  evidence: {
    previous_status: "AWAITING_APPROVAL",
    new_status: "EXECUTING",
    previous_version: 4,
    new_version: 5,
    transition_event: "APPROVED_NOW",
  },
};

export const outcomeEntry: TimelineEntry = {
  id: "aaaaaaa1-0000-4000-8000-000000000005",
  occurred_at: "2026-08-30T09:12:00Z",
  event_type: "CASE_RECOVERED",
  actor_type: "SYSTEM",
  summary: "Recovered payment verified and attributed to this case.",
  evidence: {
    outcome: "RECOVERED_BY_ACTION",
    payment_id: "pay_TESTRECOVERED",
  },
};

/** Documented warning event — the only contract-backed staleness signal. */
export const staleWebhookEntry: TimelineEntry = {
  id: "aaaaaaa1-0000-4000-8000-000000000006",
  occurred_at: "2026-08-30T09:20:00Z",
  event_type: "STALE_WEBHOOK_IGNORED",
  actor_type: "PROVIDER",
  summary: "Older payment.failed webhook ignored after verified capture.",
  evidence: {
    provider_event_id: "evt_TESTSTALE01",
  },
};

/** Raw provider event name — proves `event_type` is not a closed enum. */
export const providerRawEventEntry: TimelineEntry = {
  id: "aaaaaaa1-0000-4000-8000-000000000007",
  occurred_at: "2026-08-30T09:05:00Z",
  event_type: "payment.captured",
  actor_type: "PROVIDER",
  summary: "Provider reported a captured payment.",
  evidence: {
    webhook_event_id: "wh_TESTCAPTURE01",
  },
};

/** No evidence at all — must degrade without an empty Details disclosure. */
export const noEvidenceEntry: TimelineEntry = {
  id: "aaaaaaa1-0000-4000-8000-000000000008",
  occurred_at: "2026-08-30T08:22:00Z",
  event_type: "FAILURE_NORMALIZED",
  actor_type: "SYSTEM",
  summary: "Failure normalized to payment rail downtime.",
  evidence: {},
};

/**
 * Hostile entry: every dangerous category at once, mixed with two safe keys.
 * Only the two safe keys may render.
 */
export const unsafeEvidenceEntry: TimelineEntry = {
  id: "aaaaaaa1-0000-4000-8000-000000000009",
  occurred_at: "2026-08-30T08:45:00Z",
  event_type: "ANALYSIS_COMPLETED",
  actor_type: "MODEL",
  summary: "Analysis completed.",
  evidence: {
    // Safe — these two are the only members that may appear.
    failure_category: "PAYMENT_RAIL_DOWNTIME",
    analysis_run_id: "55555555-5555-4555-8555-555555555555",

    // PII the backend denylist would miss (key names differ from `email`/`phone`).
    customer_email: SENTINELS.email,
    email: SENTINELS.altEmail,
    customer_phone_number: SENTINELS.altPhone,
    phone: SENTINELS.phone,
    card_number: SENTINELS.cardNumber,

    // Credentials and signatures.
    authorization: SENTINELS.bearer,
    api_key: SENTINELS.apiKey,
    webhook_secret: SENTINELS.webhookSecret,
    signature: SENTINELS.signature,

    // Model internals.
    prompt: SENTINELS.prompt,
    completion: SENTINELS.completion,
    chain_of_thought: SENTINELS.chainOfThought,
    reasoning: SENTINELS.reasoning,

    // Raw payloads and internals.
    stack_trace: SENTINELS.stackTrace,
    raw_payload: { account_id: SENTINELS.rawPayloadMarker, amount: 499900 },
    webhook_body: { id: SENTINELS.rawPayloadMarker },
  },
};

/**
 * Allowlisted key names carrying the wrong types. Each must be dropped rather
 * than coerced, so a known key cannot smuggle an arbitrary payload.
 */
export const wrongTypeEvidenceEntry: TimelineEntry = {
  id: "aaaaaaa1-0000-4000-8000-00000000000a",
  occurred_at: "2026-08-30T08:50:00Z",
  event_type: "ACTION_BLOCKED_BY_POLICY",
  actor_type: "SYSTEM",
  summary: "Action blocked by policy.",
  evidence: {
    failure_category: { nested: SENTINELS.rawPayloadMarker },
    policy_reasons: [{ secret: SENTINELS.apiKey }],
    payment_id: SENTINELS.stackTrace,
    new_version: "not-a-number",
    analysis_run_id: ["array", "not", "string"],
  },
};

/** Canonical ascending-order timeline as the endpoint returns it. */
export const timelineFixture: TimelineEntry[] = [
  caseCreatedEntry,
  noEvidenceEntry,
  analysisEntry,
  policyEntry,
  executionEntry,
  providerRawEventEntry,
  outcomeEntry,
];

export function timelineResponse(items: TimelineEntry[]) {
  return { items };
}
