/**
 * Deterministic fixtures for case-detail tests only.
 *
 * Lives in a Next.js private folder (`__fixtures__`) so it is never routed, and
 * is imported exclusively from test files. Values mirror the documented
 * `API_CONTRACTS.md` case-detail example.
 */

import type {
  CaseDetail,
  CaseOutcome,
  LatestAction,
  RecommendationCandidate,
} from "@/app/(app)/recovery/[caseId]/case-types";

export const CASE_ID = "11111111-1111-4111-8111-111111111111";
export const ACTION_ID = "99999999-9999-4999-8999-999999999999";
export const ANALYSIS_RUN_ID = "55555555-5555-4555-8555-555555555555";

export const selectedCandidateFixture: RecommendationCandidate = {
  action_type: "REQUEST_ALTERNATE_PAYMENT_METHOD",
  rank: 1,
  success_probability: 0.82,
  expected_recovered_minor: 409918,
  expected_value_minor: 402500,
  policy_eligible: true,
  requires_approval: false,
  policy_reasons: [],
  execution_mode: "EXECUTABLE",
  advisory_reason_code: null,
  advisory_reason: null,
  // Reconciles exactly: 409918 - 200 - 0 - 7218 - 0 = 402500.
  erv_breakdown: {
    expected_recovered_minor: 409918,
    action_cost_minor: 200,
    fatigue_penalty_minor: 0,
    operational_risk_penalty_minor: 7218,
    delay_penalty_minor: 0,
    expected_value_minor: 402500,
  },
  factors: [
    { code: "ACTIVE_UPI_DOWNTIME", impact: "HIGH", source: "RAZORPAY_DOWNTIME" },
  ],
};

export const blockedCandidateFixture: RecommendationCandidate = {
  action_type: "RETRY_SAME_METHOD",
  rank: 2,
  success_probability: 0.31,
  expected_recovered_minor: 154969,
  expected_value_minor: 121000,
  policy_eligible: false,
  requires_approval: false,
  policy_reasons: ["ACTIVE_PAYMENT_RAIL_DOWNTIME"],
  execution_mode: "ADVISORY",
  advisory_reason_code: "NO_AUTONOMOUS_DEBIT_CAPABILITY",
  advisory_reason:
    "RevLoop holds no mandate or saved payment token for this customer, so it cannot re-attempt the original payment without the customer authorizing it again \u2014 your checkout owns that retry. RevLoop executes the highest-ranked action it can carry out itself.",
  factors: [],
};

/**
 * The model's top choice is an action RevLoop does not execute.
 *
 * Kept as its own fixture because this is the shape that produced the
 * production defect: rank 1 advisory, so a naive "selected = rank 1" read
 * offered an Execute button that always returned 422.
 */
export const advisoryTopRankedCandidateFixture: RecommendationCandidate = {
  action_type: "RETRY_SAME_METHOD",
  rank: 1,
  success_probability: 0.644,
  expected_recovered_minor: 643882,
  expected_value_minor: 641782,
  policy_eligible: true,
  requires_approval: false,
  policy_reasons: [],
  execution_mode: "ADVISORY",
  advisory_reason_code: "NO_AUTONOMOUS_DEBIT_CAPABILITY",
  advisory_reason:
    "RevLoop holds no mandate or saved payment token for this customer, so it cannot re-attempt the original payment without the customer authorizing it again \u2014 your checkout owns that retry. RevLoop executes the highest-ranked action it can carry out itself.",
  factors: [],
};

export const pendingApprovalActionFixture: LatestAction = {
  id: ACTION_ID,
  action_type: "CREATE_PAYMENT_LINK",
  status: "PENDING_APPROVAL",
  requires_approval: true,
  provider_reference: null,
  provider_status: null,
  scheduled_for: null,
  executed_at: null,
  attempt_number: 1,
};

export const waitingActionFixture: LatestAction = {
  id: ACTION_ID,
  action_type: "CREATE_PAYMENT_LINK",
  status: "SUCCEEDED",
  requires_approval: false,
  provider_reference: "plink_TESTREF123",
  provider_status: "created",
  scheduled_for: null,
  executed_at: "2026-08-30T09:00:00Z",
  attempt_number: 1,
};

/**
 * A payment-link action reached via approval, where the create-action
 * response never carried the link (ApproveRecoveryActionResponse has no
 * customer_action field). The durable source is latest_action.customer_action
 * on a subsequent case-detail GET, which this fixture represents.
 */
export const approvedActionWithLinkFixture: LatestAction = {
  ...waitingActionFixture,
  customer_action: { type: "PAYMENT_LINK", url: "https://rzp.io/i/approvedlink" },
};

export const recoveredOutcomeFixture: CaseOutcome = {
  outcome: "RECOVERED_BY_ACTION",
  recovered_amount_minor: 499900,
  recovered_at: "2026-08-30T09:12:00Z",
  recovered_payment_id: "pay_TESTRECOVERED",
  time_to_recovery_seconds: 3120,
  verification_source: "RAZORPAY_WEBHOOK",
};

/** RECOMMENDED case with a full analysis — the default demo shape. */
export const recommendedCaseFixture: CaseDetail = {
  case: {
    id: CASE_ID,
    case_type: "PAYMENT_FAILURE",
    status: "RECOMMENDED",
    amount_at_risk_minor: 499900,
    currency: "INR",
    failure_category: "PAYMENT_RAIL_DOWNTIME",
    opened_at: "2026-08-30T08:20:00Z",
    last_transition_at: "2026-08-30T08:25:00Z",
    version: 4,
  },
  customer: {
    id: "22222222-2222-4222-8222-222222222222",
    display_name: "Acme Learning",
    segment: "HIGH_VALUE",
    lifetime_value_minor: 17800000,
  },
  source: {
    type: "TRANSACTION",
    transaction_id: "33333333-3333-4333-8333-333333333333",
    provider_payment_id: "pay_TESTFAILED",
    payment_method: "upi",
    provider_status: "failed",
    failure_evidence: {
      error_code: "BAD_REQUEST_ERROR",
      error_reason: "payment_upi_rail_down",
      error_source: "bank",
      error_step: "payment_authorization",
    },
  },
  analysis: {
    analysis_run_id: ANALYSIS_RUN_ID,
    model_version: "lr-v1.0.0",
    feature_schema_version: "recovery_features_v1",
    selected_action: "REQUEST_ALTERNATE_PAYMENT_METHOD",
    confidence: 0.87,
    top_ranked_action: "REQUEST_ALTERNATE_PAYMENT_METHOD",
    candidates: [selectedCandidateFixture, blockedCandidateFixture],
    structured_explanation: {
      summary:
        "Alternative payment is preferred because the failed rail is degraded.",
      evidence: [
        "UPI rail degradation is active",
        "Customer recently paid successfully by card",
      ],
      safety: ["Amount is below automatic-action limit"],
    },
  },
  latest_action: null,
  outcome: null,
};

/** Builds a variant of the base case without mutating the shared fixture. */
export function makeCase(overrides: {
  status?: string;
  version?: number;
  analysis?: CaseDetail["analysis"];
  latestAction?: LatestAction | null;
  outcome?: CaseOutcome | null;
}): CaseDetail {
  return {
    ...recommendedCaseFixture,
    case: {
      ...recommendedCaseFixture.case,
      status: overrides.status ?? recommendedCaseFixture.case.status,
      version: overrides.version ?? recommendedCaseFixture.case.version,
    },
    analysis:
      overrides.analysis !== undefined
        ? overrides.analysis
        : recommendedCaseFixture.analysis,
    latest_action:
      overrides.latestAction !== undefined ? overrides.latestAction : null,
    outcome: overrides.outcome !== undefined ? overrides.outcome : null,
  };
}

export const detectedCaseFixture = makeCase({
  status: "DETECTED",
  analysis: null,
});

export const awaitingApprovalCaseFixture = makeCase({
  status: "AWAITING_APPROVAL",
  latestAction: pendingApprovalActionFixture,
});

export const waitingForOutcomeCaseFixture = makeCase({
  status: "WAITING_FOR_OUTCOME",
  latestAction: waitingActionFixture,
});

export const recoveredCaseFixture = makeCase({
  status: "RECOVERED",
  latestAction: waitingActionFixture,
  outcome: recoveredOutcomeFixture,
});

export const failedCaseFixture = makeCase({ status: "FAILED" });

export const stoppedCaseFixture = makeCase({ status: "STOPPED" });

export const executingCaseFixture = makeCase({
  status: "EXECUTING",
  latestAction: { ...waitingActionFixture, status: "EXECUTING" },
});

export const scheduledCaseFixture = makeCase({
  status: "SCHEDULED",
  latestAction: {
    ...waitingActionFixture,
    status: "SCHEDULED",
    scheduled_for: "2026-08-30T12:00:00Z",
    provider_reference: null,
  },
});
