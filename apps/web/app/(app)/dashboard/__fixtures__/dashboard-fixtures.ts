/**
 * Deterministic fixtures for dashboard tests only.
 *
 * This module lives in a Next.js private folder (`__fixtures__`) so it is never
 * routed, and it is imported exclusively from test files. No production code
 * path reads these values.
 */

import type {
  DashboardSummary,
  RecoveryCaseListItem,
  RecoveryCaseListResponse,
} from "@/app/(app)/dashboard/dashboard-types";

export const dashboardSummaryFixture: DashboardSummary = {
  currency: "INR",
  revenue_at_risk_minor: 48200000,
  revenue_recovered_minor: 31600000,
  baseline_recovered_minor: 23400000,
  baseline_assumption: {
    kind: "MODELLED_COUNTERFACTUAL",
    naive_recovery_rate: 0.4,
    naive_actions: ["RETRY_SAME_METHOD", "WAIT"],
    description:
      "Modelled counterfactual, not a measured control group. Where the naive policy would have chosen the same action RevLoop did (RETRY_SAME_METHOD or WAIT), it is credited with the same expected recovery; otherwise it is assumed to recover 40% of the amount at risk. No untreated holdout exists in this dataset, so this is an assumption, not an observation.",
  },
  incremental_recovered_minor: 8200000,
  recovery_rate: 0.655602,
  active_cases: 47,
  recovered_cases: 61,
  average_recovery_seconds: 5130,
  recovery_trend: [
    { date: "2026-08-29", at_risk_minor: 9200000, recovered_minor: 6100000 },
    { date: "2026-08-30", at_risk_minor: 10400000, recovered_minor: 7250000 },
    { date: "2026-08-31", at_risk_minor: 8800000, recovered_minor: 5900000 },
  ],
  action_effectiveness: [
    {
      action_type: "REQUEST_ALTERNATE_PAYMENT_METHOD",
      attempted: 21,
      recovered: 15,
      recovery_rate: 0.714286,
      recovered_minor: 8700000,
    },
    {
      action_type: "RETRY_PAYMENT",
      attempted: 34,
      recovered: 18,
      recovery_rate: 0.529412,
      recovered_minor: 9400000,
    },
  ],
  failure_breakdown: [
    {
      failure_category: "PAYMENT_RAIL_DOWNTIME",
      cases: 18,
      amount_minor: 6600000,
    },
    {
      failure_category: "INSUFFICIENT_FUNDS",
      cases: 11,
      amount_minor: 4100000,
    },
  ],
  source_label: "SYNTHETIC_DEMO",
};

/** All-zero summary used to exercise the empty dashboard state. */
export const emptyDashboardSummaryFixture: DashboardSummary = {
  currency: "INR",
  revenue_at_risk_minor: 0,
  revenue_recovered_minor: 0,
  baseline_recovered_minor: 0,
  baseline_assumption: {
    kind: "MODELLED_COUNTERFACTUAL",
    naive_recovery_rate: 0.4,
    naive_actions: ["RETRY_SAME_METHOD", "WAIT"],
    description:
      "Modelled counterfactual, not a measured control group. Where the naive policy would have chosen the same action RevLoop did (RETRY_SAME_METHOD or WAIT), it is credited with the same expected recovery; otherwise it is assumed to recover 40% of the amount at risk. No untreated holdout exists in this dataset, so this is an assumption, not an observation.",
  },
  incremental_recovered_minor: 0,
  recovery_rate: 0,
  active_cases: 0,
  recovered_cases: 0,
  average_recovery_seconds: null,
  recovery_trend: [],
  action_effectiveness: [],
  failure_breakdown: [],
  source_label: "SYNTHETIC_DEMO",
};

/**
 * Summary whose nullable contract fields are absent, used to prove the UI shows
 * a dash instead of inventing a value.
 */
export const sparseDashboardSummaryFixture: DashboardSummary = {
  ...dashboardSummaryFixture,
  average_recovery_seconds: null,
  recovery_trend: [
    { date: "2026-08-31", at_risk_minor: 0, recovered_minor: 0 },
  ],
  action_effectiveness: [],
  failure_breakdown: [],
};

export const topOpportunityFixture: RecoveryCaseListItem = {
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

/** Case whose optional scoring fields are null. */
export const unscoredOpportunityFixture: RecoveryCaseListItem = {
  id: "33333333-3333-4333-8333-333333333333",
  customer: {
    id: "44444444-4444-4444-8444-444444444444",
    display_name: "Northwind Subscriptions International Holdings",
    segment: "STANDARD",
  },
  case_type: "PAYMENT_FAILURE",
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

export const topOpportunitiesFixture: RecoveryCaseListResponse = {
  items: [topOpportunityFixture, unscoredOpportunityFixture],
  total: 2,
  limit: 5,
  offset: 0,
};

export const emptyTopOpportunitiesFixture: RecoveryCaseListResponse = {
  items: [],
  total: 0,
  limit: 5,
  offset: 0,
};
