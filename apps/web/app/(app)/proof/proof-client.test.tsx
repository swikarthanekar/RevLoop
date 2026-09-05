import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProofClient } from "@/app/(app)/proof/proof-client";
import { ApiClient } from "@/lib/api/api-client";
import { NullAccessTokenProvider } from "@/lib/auth/token-provider";
import type { CachedEvaluation } from "@/app/(app)/proof/proof-types";

const EVALUATION: CachedEvaluation = {
  computed_at: "2026-09-05T09:56:17.489855Z",
  duration_seconds: 9.606,
  recomputed: false,
  evaluation: {
    data_source: "SYNTHETIC_SIMULATION",
    evaluation_label: "SYNTHETIC POLICY SIMULATION",
    scorer: {
      model_version: "lr-v1.0.0",
      model_family: "logistic_regression",
      feature_schema_version: "recovery_features_v1",
    },
    dataset: {
      dataset_version: "synthetic_recovery_v1",
      seed: 20260901,
      split: "test",
      case_count: 250,
    },
    revloop_model_policy: {
      number_of_cases: 250,
      amount_at_risk_minor: 351820768,
      expected_synthetic_recovered_minor: 110130208,
      realized_synthetic_recovered_minor: 105704376,
      realized_recovery_rate: "0.2880",
      selected_intervention_count: 250,
      contact_action_count: 0,
      stop_count: 0,
      no_selection_count: 0,
    },
    naive_baseline_policy: {
      number_of_cases: 250,
      amount_at_risk_minor: 351820768,
      expected_synthetic_recovered_minor: 78474975,
      realized_synthetic_recovered_minor: 82019979,
      realized_recovery_rate: "0.2240",
      selected_intervention_count: 221,
      contact_action_count: 0,
      stop_count: 29,
      no_selection_count: 0,
    },
    incremental_expected_recovered_minor: 31655233,
    incremental_realized_recovered_minor: 23952416,
  },
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    text: async () => JSON.stringify(body),
  } as Response;
}

function buildClient(
  routeFor: (url: string, method: string) => { status: number; body: unknown },
) {
  const fetchImpl = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const route = routeFor(String(input), init?.method ?? "GET");
      return jsonResponse(route.status, route.body);
    },
  );
  const client = new ApiClient({
    baseUrl: "http://api.test",
    tokenProvider: new NullAccessTokenProvider(),
    fetchImpl: fetchImpl as unknown as typeof fetch,
  });
  return { client, fetchImpl };
}

function renderWith(client: ApiClient) {
  return render(<ProofClient apiClient={client} />);
}

describe("ProofClient", () => {
  it("renders both policies and the uplift between them", async () => {
    const { client } = buildClient(() => ({ status: 200, body: EVALUATION }));
    renderWith(client);

    expect(await screen.findByText("28.80%")).toBeInTheDocument();
    expect(screen.getByText("22.40%")).toBeInTheDocument();
    // 28.80 - 22.40 = 6.40 points.
    expect(screen.getByText("+6.40 pts")).toBeInTheDocument();
  });

  it("states the synthetic provenance prominently, not in a footnote", async () => {
    const { client } = buildClient(() => ({ status: 200, body: EVALUATION }));
    renderWith(client);

    expect(
      await screen.findByText("SYNTHETIC POLICY SIMULATION"),
    ).toBeInTheDocument();
    expect(screen.getByText(/not from merchant traffic/i)).toBeInTheDocument();
    // The seed and split must be visible so the run can be reproduced.
    expect(screen.getByText("20260901")).toBeInTheDocument();
    expect(screen.getByText(/test \(held out\)/i)).toBeInTheDocument();
    expect(screen.getAllByText(/lr-v1\.0\.0/).length).toBeGreaterThan(0);
  });

  it("says when the figures were computed and that they are cached", async () => {
    const { client } = buildClient(() => ({ status: 200, body: EVALUATION }));
    renderWith(client);
    expect(await screen.findByText(/served from cache/i)).toBeInTheDocument();
  });

  it("recomputes on demand and reports the fresh run", async () => {
    const { client, fetchImpl } = buildClient((url, method) => {
      if (method === "POST") {
        return {
          status: 200,
          body: {
            ...EVALUATION,
            computed_at: "2026-09-05T10:10:00.000000Z",
            recomputed: true,
          },
        };
      }
      return { status: 200, body: EVALUATION };
    });
    renderWith(client);

    await screen.findByText("28.80%");
    fireEvent.click(screen.getByRole("button", { name: /recompute/i }));

    await waitFor(() =>
      expect(screen.getByText(/just recomputed/i)).toBeInTheDocument(),
    );
    // Determinism: the figures are unchanged after a fresh run.
    expect(screen.getByText("28.80%")).toBeInTheDocument();
    expect(
      fetchImpl.mock.calls.some(([, init]) => (init as RequestInit)?.method === "POST"),
    ).toBe(true);
  });

  it("keeps the last good figures when a recompute fails", async () => {
    const { client } = buildClient((url, method) => {
      if (method === "POST") {
        return { status: 503, body: { error: { code: "X", message: "nope" } } };
      }
      return { status: 200, body: EVALUATION };
    });
    renderWith(client);

    await screen.findByText("28.80%");
    fireEvent.click(screen.getByRole("button", { name: /recompute/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/recompute failed/i),
    );
    // A failed refresh must annotate the page, never blank the evidence.
    expect(screen.getByText("28.80%")).toBeInTheDocument();
  });

  it("shows an error state when the evaluation cannot be loaded at all", async () => {
    const { client } = buildClient(() => ({
      status: 503,
      body: { error: { code: "CANONICAL_EVALUATION_UNAVAILABLE", message: "no" } },
    }));
    renderWith(client);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
