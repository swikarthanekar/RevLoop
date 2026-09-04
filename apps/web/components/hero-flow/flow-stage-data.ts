/**
 * Maps real dashboard figures onto the four stages the revenue-flow scene
 * renders. This is presentation-only derivation for a visualization -- it
 * never feeds back into any financial computation and the underlying numbers
 * always come from the backend-supplied `DashboardSummary`.
 */

export interface FlowStage {
  id: "at_risk" | "decision" | "recovery" | "recovered";
  label: string;
  sublabel: string;
  colorHex: string;
  /** 0..1, drives node size and particle density for this stage. */
  intensity: number;
}

/** Clamped log-ish normalization so one huge outlier doesn't flatten the rest. */
function normalize(value: number, referenceMax: number): number {
  if (!Number.isFinite(value) || value <= 0 || referenceMax <= 0) {
    return 0.12;
  }
  const ratio = Math.log10(1 + value) / Math.log10(1 + referenceMax);
  return Math.min(1, Math.max(0.12, ratio));
}

export interface FlowSourceMetrics {
  revenueAtRiskMinor: number;
  revenueRecoveredMinor: number;
  activeCases: number;
  recoveredCases: number;
  recoveryRate: number;
}

export function buildFlowStages(metrics: FlowSourceMetrics): FlowStage[] {
  const moneyReference = Math.max(
    metrics.revenueAtRiskMinor,
    metrics.revenueRecoveredMinor,
    1,
  );
  const caseReference = Math.max(
    metrics.activeCases,
    metrics.recoveredCases,
    1,
  );

  return [
    {
      id: "at_risk",
      label: "At Risk",
      sublabel: "Payment failures detected",
      colorHex: "#f59e0b",
      intensity: normalize(metrics.revenueAtRiskMinor, moneyReference),
    },
    {
      id: "decision",
      label: "AI Decision",
      sublabel: "Policy-checked recommendation",
      colorHex: "#818cf8",
      intensity: normalize(metrics.activeCases, caseReference),
    },
    {
      id: "recovery",
      label: "Recovery",
      sublabel: "Action executing",
      colorHex: "#22d3ee",
      intensity: Math.min(1, Math.max(0.12, metrics.recoveryRate + 0.15)),
    },
    {
      id: "recovered",
      label: "Recovered",
      sublabel: "Verified via webhook",
      colorHex: "#34d399",
      intensity: normalize(metrics.revenueRecoveredMinor, moneyReference),
    },
  ];
}
