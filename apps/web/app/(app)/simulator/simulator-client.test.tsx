import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SimulatorClient } from "@/app/(app)/simulator/simulator-client";
import type { SimulationResponse } from "@/app/(app)/simulator/simulator-types";

/**
 * The simulator page builds its own client inside `useSimulation`, so the hook
 * is stubbed here. What is under test is the presentation contract: that the
 * page renders the server's decision faithfully and never derives a number of
 * its own.
 */
const mockUseSimulation = vi.fn();
vi.mock("@/app/(app)/simulator/use-simulation", () => ({
  SIMULATE_PATH: "/api/v1/simulator/score",
  SIMULATE_DEBOUNCE_MS: 0,
  useSimulation: (...args: unknown[]) => mockUseSimulation(...args),
}));

const RESPONSE: SimulationResponse = {
  data_source: "INTERACTIVE_SIMULATION",
  selected_action: "REQUEST_ALTERNATE_PAYMENT_METHOD",
  top_ranked_action: "RETRY_SAME_METHOD",
  currency: "INR",
  amount_at_risk_minor: 199900,
  model_version: "lr-v1.0.0",
  model_family: "logistic_regression",
  feature_schema_version: "recovery_features_v1",
  inference_source: "model",
  policy_auto_action_limit_minor: 1000000,
  policy_minimum_auto_confidence: 0.7,
  candidates: [
    {
      action_type: "RETRY_SAME_METHOD",
      rank: 1,
      success_probability: 0.8622,
      confidence: 0.81,
      expected_recovered_minor: 172353,
      action_cost_minor: 100,
      fatigue_penalty_minor: 0,
      operational_risk_penalty_minor: 395,
      delay_penalty_minor: 0,
      expected_value_minor: 171858,
      policy_eligible: true,
      requires_approval: false,
      policy_reasons: [],
      execution_mode: "ADVISORY",
      advisory_reason:
        "RevLoop holds no mandate or saved payment token for this customer.",
      selected: false,
    },
    {
      action_type: "REQUEST_ALTERNATE_PAYMENT_METHOD",
      rank: 2,
      success_probability: 0.8547,
      confidence: 0.8,
      expected_recovered_minor: 170854,
      action_cost_minor: 200,
      fatigue_penalty_minor: 0,
      operational_risk_penalty_minor: 296,
      delay_penalty_minor: 0,
      expected_value_minor: 170358,
      policy_eligible: true,
      requires_approval: false,
      policy_reasons: [],
      execution_mode: "EXECUTABLE",
      advisory_reason: null,
      selected: true,
    },
  ],
};

function stub(data: SimulationResponse) {
  mockUseSimulation.mockReturnValue({
    state: { status: "ready", data },
    isRefreshing: false,
  });
}

describe("SimulatorClient", () => {
  it("shows the action the engine would execute", async () => {
    stub(RESPONSE);
    render(<SimulatorClient />);
    // "Would execute" appears twice on purpose: as the panel heading and as
    // the badge on the chosen row.
    expect((await screen.findAllByText("Would execute")).length).toBe(2);
    expect(
      screen.getAllByText(/Request alternate payment method/i).length,
    ).toBeGreaterThan(0);
  });

  it("marks the advisory rank-1 action and explains why it is not executed", async () => {
    stub(RESPONSE);
    render(<SimulatorClient />);
    expect(await screen.findByText("Advisory")).toBeInTheDocument();
    expect(
      screen.getByText(/no mandate or saved payment token/i),
    ).toBeInTheDocument();
    // The divergence is stated rather than left for the reader to spot.
    expect(screen.getByText(/does not execute it/i)).toBeInTheDocument();
  });

  it("attributes the probabilities to the real model", async () => {
    stub(RESPONSE);
    render(<SimulatorClient />);
    // Model provenance is stated on the decision panel, including whether the
    // probabilities came from the model or a heuristic fallback.
    expect(
      await screen.findByText(/Model lr-v1\.0\.0/),
    ).toBeInTheDocument();
    expect(screen.getByText("model")).toBeInTheDocument();
  });

  it("reveals the ERV arithmetic on demand", async () => {
    stub(RESPONSE);
    render(<SimulatorClient />);

    const toggles = await screen.findAllByRole("button", {
      name: /show the arithmetic/i,
    });
    fireEvent.click(toggles[0]);

    await waitFor(() =>
      expect(screen.getByText(/How expected value is derived/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Action cost/)).toBeInTheDocument();
  });

  it("labels the output as a simulation that stores nothing", async () => {
    stub(RESPONSE);
    render(<SimulatorClient />);
    expect(
      await screen.findByText(/No case is created and\s+nothing is stored/i),
    ).toBeInTheDocument();
  });

  it("surfaces a policy verdict of requires-approval", async () => {
    stub({
      ...RESPONSE,
      candidates: RESPONSE.candidates.map((candidate) => ({
        ...candidate,
        requires_approval: true,
        policy_reasons: ["AMOUNT_ABOVE_AUTO_ACTION_LIMIT"],
      })),
    });
    render(<SimulatorClient />);
    expect(
      (await screen.findAllByText(/requires approval/i)).length,
    ).toBeGreaterThan(0);
  });

  it("renders an error state without crashing the controls", async () => {
    mockUseSimulation.mockReturnValue({
      state: {
        status: "error",
        error: {
          kind: "http",
          status: 503,
          code: "SIMULATION_UNAVAILABLE",
          safeMessage: "unavailable",
          requestId: null,
        },
      },
      isRefreshing: false,
    });
    render(<SimulatorClient />);
    // The scenario controls stay usable so the reader can change and retry.
    expect(
      await screen.findByText(/Failure category/i),
    ).toBeInTheDocument();
  });
});
