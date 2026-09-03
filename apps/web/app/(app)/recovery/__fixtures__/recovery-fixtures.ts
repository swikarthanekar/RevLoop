/**
 * Deterministic fixtures for recovery list tests only.
 *
 * This module lives in a Next.js private folder (`__fixtures__`) so it is never
 * routed, and it is imported exclusively from test files.
 */

import type {
  RecoveryCaseListItem,
  RecoveryCaseListResponse,
} from "@/app/(app)/recovery/recovery-types";

/** Fully scored, high-value case matching the documented contract example. */
export const scoredCaseFixture: RecoveryCaseListItem = {
  id: "11111111-1111-4111-8111-111111111111",
  customer: {
    id: "22222222-2222-4222-8222-222222222222",
    display_name: "Acme Learning",
    segment: "HIGH_VALUE",
  },
  case_type: "PAYMENT_FAILURE",
  amount_at_risk_minor: 499900,
  currency: "INR",
  failure_category: "PAYMENT_RAIL_DOWNTIME",
  status: "RECOMMENDED",
  priority_score: 0.8912,
  recovery_probability: 0.82,
  expected_recoverable_minor: 409918,
  recommended_action: "REQUEST_ALTERNATE_PAYMENT_METHOD",
  confidence: 0.87,
  opened_at: "2026-08-30T08:20:00Z",
};

/** Newly detected case whose optional scoring fields are still null. */
export const unscoredCaseFixture: RecoveryCaseListItem = {
  id: "33333333-3333-4333-8333-333333333333",
  customer: {
    id: "44444444-4444-4444-8444-444444444444",
    display_name: "Northwind Subscriptions",
    segment: "STANDARD",
  },
  case_type: "SUBSCRIPTION_FAILURE",
  amount_at_risk_minor: 125000,
  currency: "INR",
  failure_category: null,
  status: "DETECTED",
  priority_score: null,
  recovery_probability: null,
  expected_recoverable_minor: null,
  recommended_action: null,
  confidence: null,
  opened_at: "2026-08-31T11:05:00Z",
};

export const recoveryListFixture: RecoveryCaseListResponse = {
  items: [scoredCaseFixture, unscoredCaseFixture],
  total: 2,
  limit: 25,
  offset: 0,
};

/** Multi-page response used to exercise pagination controls. */
export const pagedRecoveryListFixture: RecoveryCaseListResponse = {
  items: [scoredCaseFixture, unscoredCaseFixture],
  total: 47,
  limit: 25,
  offset: 0,
};

export const emptyRecoveryListFixture: RecoveryCaseListResponse = {
  items: [],
  total: 0,
  limit: 25,
  offset: 0,
};
