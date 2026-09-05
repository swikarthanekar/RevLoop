import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ErvWaterfall } from "@/app/(app)/simulator/erv-waterfall";
import { formatMoney } from "@/lib/money/format-money";

const RECONCILING = {
  currency: "INR",
  expectedRecoveredMinor: 409918,
  actionCostMinor: 200,
  fatiguePenaltyMinor: 0,
  operationalRiskPenaltyMinor: 7218,
  delayPenaltyMinor: 0,
  expectedValueMinor: 402500,
};

describe("ErvWaterfall", () => {
  it("shows every non-zero component and the server's own total", () => {
    render(<ErvWaterfall {...RECONCILING} />);

    expect(screen.getByText(formatMoney(409918, "INR"))).toBeInTheDocument();
    expect(screen.getByText(/Action cost/)).toBeInTheDocument();
    expect(screen.getByText(/Operational risk/)).toBeInTheDocument();
    expect(screen.getByText(formatMoney(402500, "INR"))).toBeInTheDocument();
  });

  it("omits components that are zero rather than printing empty rows", () => {
    render(<ErvWaterfall {...RECONCILING} />);
    // Fatigue and delay are both zero for this action.
    expect(screen.queryByText(/Contact fatigue/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Delay penalty/)).not.toBeInTheDocument();
  });

  it("renders the total the server supplied, not a locally recomputed sum", () => {
    // Deliberately inconsistent input. The component must display the server's
    // `expectedValueMinor` verbatim; if it silently recomputed the total it
    // would always agree with itself and a backend discrepancy would be
    // invisible. Reconciliation is enforced server-side.
    render(
      <ErvWaterfall
        {...RECONCILING}
        expectedValueMinor={1}
      />,
    );
    expect(screen.getByText(formatMoney(1, "INR"))).toBeInTheDocument();
    expect(
      screen.queryByText(formatMoney(402500, "INR")),
    ).not.toBeInTheDocument();
  });

  it("says the figures are computed server-side", () => {
    render(<ErvWaterfall {...RECONCILING} />);
    expect(
      screen.getByText(/browser never recalculates these figures/i),
    ).toBeInTheDocument();
  });

  it("handles an action with no deductions at all", () => {
    render(
      <ErvWaterfall
        currency="INR"
        expectedRecoveredMinor={100000}
        actionCostMinor={0}
        fatiguePenaltyMinor={0}
        operationalRiskPenaltyMinor={0}
        delayPenaltyMinor={0}
        expectedValueMinor={100000}
      />,
    );
    expect(screen.getByText(/No deductions apply/i)).toBeInTheDocument();
  });
});
