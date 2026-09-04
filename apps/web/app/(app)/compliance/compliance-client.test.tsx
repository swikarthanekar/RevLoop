import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ComplianceClient } from "@/app/(app)/compliance/compliance-client";
import { POLICY_PATH } from "@/app/(app)/compliance/use-compliance-data";
import {
  automationDisabledPolicyFixture,
  policyFixture,
} from "@/app/(app)/compliance/__fixtures__/compliance-fixtures";
import { ApiClient } from "@/lib/api/api-client";
import { NullAccessTokenProvider } from "@/lib/auth/token-provider";
import { formatMoney } from "@/lib/money/format-money";

type RouteBody = { status: number; body: unknown };

function jsonResponse({ status, body }: RouteBody): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    text: async () => JSON.stringify(body),
  } as Response;
}

function buildClient(
  routeFor: (url: string, callIndex: number) => RouteBody | Promise<RouteBody>,
) {
  let callIndex = 0;
  const fetchImpl = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
    const url = String(input);
    const route = await routeFor(url, callIndex);
    callIndex += 1;
    return jsonResponse(route);
  });

  const client = new ApiClient({
    baseUrl: "http://api.test",
    tokenProvider: new NullAccessTokenProvider(),
    fetchImpl: fetchImpl as unknown as typeof fetch,
  });

  return { client, fetchImpl };
}

function happyPathClient(policy = policyFixture) {
  return buildClient((url) => {
    if (url.includes(POLICY_PATH)) {
      return { status: 200, body: policy };
    }
    return { status: 404, body: { error: { code: "NOT_FOUND", message: "unexpected" } } };
  });
}

describe("ComplianceClient", () => {
  it("renders the enforced policy from a representative API response", async () => {
    const { client } = happyPathClient();
    render(<ComplianceClient apiClient={client} />);

    expect(
      await screen.findByRole("heading", { name: "Compliance Guardrails", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Enabled")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("1h 30m")).toBeInTheDocument();
  });

  it("requests the documented policy endpoint", async () => {
    const { client, fetchImpl } = happyPathClient();
    render(<ComplianceClient apiClient={client} />);

    await screen.findByRole("heading", { name: "Compliance Guardrails", level: 1 });

    const requestedUrls = fetchImpl.mock.calls.map(([input]) => String(input));
    expect(requestedUrls.some((url) => url.endsWith(POLICY_PATH))).toBe(true);
  });

  it("formats the auto-action limit with the centralized money formatter", async () => {
    const { client } = happyPathClient();
    render(<ComplianceClient apiClient={client} />);

    const expected = formatMoney(
      policyFixture.auto_action_limit_minor,
      policyFixture.currency,
    );
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });

  it("groups action types under allowed, manual-approval and cooldown sections", async () => {
    const { client } = happyPathClient();
    render(<ComplianceClient apiClient={client} />);

    expect(
      await screen.findByRole("heading", { name: "Allowed actions", level: 3 }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Requires manual approval", level: 3 }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Subject to contact cooldown", level: 3 }),
    ).toBeInTheDocument();

    const manualApprovalSection = screen
      .getByRole("heading", { name: "Requires manual approval", level: 3 })
      .closest("div");
    expect(manualApprovalSection).not.toBeNull();
    expect(manualApprovalSection).toHaveTextContent("Escalate to human");
  });

  it("shows automation as disabled when the policy has it off", async () => {
    const { client } = happyPathClient(automationDisabledPolicyFixture);
    render(<ComplianceClient apiClient={client} />);

    expect(await screen.findByText("Disabled")).toBeInTheDocument();
    expect(
      screen.getByText("Every action currently requires manual approval"),
    ).toBeInTheDocument();
  });

  it("shows an accessible skeleton while the policy loads", async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });

    const { client } = buildClient(async (url) => {
      if (url.includes(POLICY_PATH)) {
        await gate;
      }
      return { status: 200, body: policyFixture };
    });

    const { container } = render(<ComplianceClient apiClient={client} />);

    expect(screen.getByText("Loading compliance guardrails")).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByText("Automation")).not.toBeInTheDocument();

    release?.();
    expect(await screen.findByText("Automation")).toBeInTheDocument();
  });

  it("renders a localized error with retry and recovers on success", async () => {
    const { client } = buildClient((url, callIndex) => {
      if (url.includes(POLICY_PATH)) {
        if (callIndex === 0) {
          return {
            status: 404,
            body: {
              error: {
                code: "POLICY_NOT_FOUND",
                message: "No policy configured.",
                request_id: "req_policy_1",
              },
            },
          };
        }
        return { status: 200, body: policyFixture };
      }
      return { status: 404, body: { error: { code: "NOT_FOUND", message: "unexpected" } } };
    });

    render(<ComplianceClient apiClient={client} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toBeInTheDocument();

    const retryButton = screen.getByRole("button", { name: "Retry" });
    retryButton.click();

    expect(
      await screen.findByRole("heading", { name: "Compliance Guardrails", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
