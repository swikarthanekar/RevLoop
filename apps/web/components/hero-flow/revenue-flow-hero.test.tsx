import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RevenueFlowHero } from "@/components/hero-flow/revenue-flow-hero";

const metrics = {
  revenueAtRiskMinor: 500000,
  revenueRecoveredMinor: 200000,
  activeCases: 12,
  recoveredCases: 4,
  recoveryRate: 0.4,
};

describe("RevenueFlowHero", () => {
  it("renders an accessible summary of all four pipeline stages", async () => {
    render(<RevenueFlowHero metrics={metrics} />);

    const region = await screen.findByRole("img", {
      name: /At Risk to AI Decision to Recovery to Recovered/i,
    });
    expect(region).toBeInTheDocument();
  });

  it("degrades to the static fallback when WebGL is unavailable (as in this test environment)", async () => {
    render(<RevenueFlowHero metrics={metrics} />);

    // jsdom has no WebGL context, so the Canvas branch never mounts and the
    // static gradient fallback renders every stage label instead.
    expect(await screen.findByText("At Risk")).toBeInTheDocument();
    expect(screen.getByText("AI Decision")).toBeInTheDocument();
    expect(screen.getByText("Recovery")).toBeInTheDocument();
    expect(screen.getByText("Recovered")).toBeInTheDocument();
  });

  it("never crashes on an all-zero metrics snapshot (empty workspace)", async () => {
    render(
      <RevenueFlowHero
        metrics={{
          revenueAtRiskMinor: 0,
          revenueRecoveredMinor: 0,
          activeCases: 0,
          recoveredCases: 0,
          recoveryRate: 0,
        }}
      />,
    );

    expect(await screen.findByText("At Risk")).toBeInTheDocument();
  });
});
