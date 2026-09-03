import type { components } from "@/types/generated/api";

/**
 * Backend-authoritative contracts, aliased from the generated OpenAPI schema.
 * The case detail view never redefines a domain shape by hand.
 */
export type CaseDetail = components["schemas"]["RecoveryCaseDetailResponse"];
export type CaseCore = components["schemas"]["CaseCore"];
export type CustomerDetail = components["schemas"]["CustomerDetail"];
export type CaseAnalysis = components["schemas"]["CaseAnalysis"];
export type RecommendationCandidate =
  components["schemas"]["RecommendationCandidate"];
export type RecommendationFactor = components["schemas"]["RecommendationFactor"];
export type StructuredExplanation = components["schemas"]["StructuredExplanation"];
export type LatestAction = components["schemas"]["LatestAction"];
export type CaseOutcome = components["schemas"]["CaseOutcome"];
export type SourceTransaction = components["schemas"]["SourceTransaction"];
export type SourceSubscription = components["schemas"]["SourceSubscription"];
export type CaseSource = CaseDetail["source"];

export type RecoveryActionType = components["schemas"]["RecoveryActionType"];
export type AnalysisReason = components["schemas"]["AnalysisReason"];

export type AnalyzeRecoveryCaseResponse =
  components["schemas"]["AnalyzeRecoveryCaseResponse"];
export type CreateRecoveryActionResponse =
  components["schemas"]["CreateRecoveryActionResponse"];
export type ApproveRecoveryActionResponse =
  components["schemas"]["ApproveRecoveryActionResponse"];
export type RejectRecoveryActionResponse =
  components["schemas"]["RejectRecoveryActionResponse"];
export type CustomerActionResponse = components["schemas"]["CustomerActionResponse"];

/**
 * Terminal states per STATE_MACHINE.md section 1. Used for presentation only —
 * the backend rejects mutations on terminal cases regardless of what the UI shows.
 */
export const TERMINAL_STATUSES = ["RECOVERED", "FAILED", "STOPPED"] as const;

export function isTerminalStatus(status: string): boolean {
  return (TERMINAL_STATUSES as readonly string[]).includes(status);
}

/** Narrows the polymorphic `source` union using its discriminator. */
export function isTransactionSource(
  source: CaseSource,
): source is SourceTransaction {
  return source.type === "TRANSACTION";
}

export function isSubscriptionSource(
  source: CaseSource,
): source is SourceSubscription {
  return source.type === "SUBSCRIPTION";
}
