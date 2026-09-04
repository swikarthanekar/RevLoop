import { describe, expect, it } from "vitest";

import { buildFlowStages } from "@/components/hero-flow/flow-stage-data";

describe("buildFlowStages", () => {
  it("returns exactly the four flow stages in order", () => {
    const stages = buildFlowStages({
      revenueAtRiskMinor: 500000,
      revenueRecoveredMinor: 200000,
      activeCases: 12,
      recoveredCases: 4,
      recoveryRate: 0.4,
    });

    expect(stages.map((stage) => stage.id)).toEqual([
      "at_risk",
      "decision",
      "recovery",
      "recovered",
    ]);
  });

  it("clamps every intensity into a renderable 0..1 range", () => {
    const stages = buildFlowStages({
      revenueAtRiskMinor: 9_999_999_999,
      revenueRecoveredMinor: 1,
      activeCases: 0,
      recoveredCases: 0,
      recoveryRate: 0,
    });

    for (const stage of stages) {
      expect(stage.intensity).toBeGreaterThanOrEqual(0.12);
      expect(stage.intensity).toBeLessThanOrEqual(1);
    }
  });

  it("degrades to a visible minimum intensity when all inputs are zero", () => {
    const stages = buildFlowStages({
      revenueAtRiskMinor: 0,
      revenueRecoveredMinor: 0,
      activeCases: 0,
      recoveredCases: 0,
      recoveryRate: 0,
    });

    for (const stage of stages) {
      expect(Number.isFinite(stage.intensity)).toBe(true);
      expect(stage.intensity).toBeGreaterThan(0);
    }
  });
});
