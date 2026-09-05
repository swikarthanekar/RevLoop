import type { components } from "@/types/generated/api";

/**
 * Backend-authoritative contracts. These are aliases over the generated OpenAPI
 * schema so the dashboard never redefines a domain shape by hand.
 */
export type DashboardSummary = components["schemas"]["DashboardSummaryResponse"];
export type RecoveryTrendPoint = components["schemas"]["RecoveryTrendPoint"];
export type ActionEffectivenessRow = components["schemas"]["ActionEffectivenessRow"];
export type FailureBreakdownRow = components["schemas"]["FailureBreakdownRow"];
export type RecoveryCaseListItem = components["schemas"]["RecoveryCaseListItem"];
export type RecoveryCaseListResponse =
  components["schemas"]["RecoveryCaseListResponse"];

/**
 * Everything the dashboard renders in its ready state. `topOpportunities` is
 * best-effort: the summary drives the page, the case list enriches it.
 */
export interface DashboardData {
  summary: DashboardSummary;
  topOpportunities: RecoveryCaseListItem[];
  topOpportunitiesUnavailable: boolean;
}

/**
 * The dashboard is empty when the backend reports no money and no case activity.
 * Absence of data is never replaced with invented metrics.
 */
export function isDashboardEmpty(summary: DashboardSummary): boolean {
  return (
    summary.revenue_at_risk_minor === 0 &&
    summary.revenue_recovered_minor === 0 &&
    summary.active_cases === 0 &&
    summary.recovered_cases === 0 &&
    summary.recovery_trend.length === 0 &&
    summary.action_effectiveness.length === 0 &&
    summary.failure_breakdown.length === 0
  );
}

export type BaselineAssumption =
  components["schemas"]["BaselineAssumption"];
