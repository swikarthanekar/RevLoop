import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode;
    href: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import { CaseDetailClient } from "@/app/(app)/recovery/[caseId]/case-detail-client";
import { ApiClient } from "@/lib/api/api-client";
import { NullAccessTokenProvider } from "@/lib/auth/token-provider";
import { formatMoney } from "@/lib/money/format-money";
import {
  ACTION_ID,
  ANALYSIS_RUN_ID,
  CASE_ID,
  approvedActionWithLinkFixture,
  awaitingApprovalCaseFixture,
  detectedCaseFixture,
  executingCaseFixture,
  failedCaseFixture,
  makeCase,
  recommendedCaseFixture,
  recoveredCaseFixture,
  scheduledCaseFixture,
  stoppedCaseFixture,
  waitingForOutcomeCaseFixture,
} from "@/app/(app)/recovery/[caseId]/__fixtures__/case-fixtures";

interface RouteBody {
  status: number;
  body: unknown;
}

interface CallRecord {
  url: string;
  method: string;
  body: unknown;
}

function jsonResponse({ status, body }: RouteBody): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    text: async () => JSON.stringify(body),
  } as Response;
}

/**
 * Builds a client on the real transport so tests exercise the shared ApiClient
 * and its error-envelope parsing rather than a hand-rolled stub.
 */
function buildClient(
  routeFor: (call: CallRecord, callIndex: number) => RouteBody,
) {
  const calls: CallRecord[] = [];

  const fetchImpl = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const record: CallRecord = {
        url: String(input),
        method: (init?.method ?? "GET").toUpperCase(),
        body:
          typeof init?.body === "string"
            ? (JSON.parse(init.body) as unknown)
            : null,
      };
      calls.push(record);
      return jsonResponse(routeFor(record, calls.length - 1));
    },
  );

  const client = new ApiClient({
    baseUrl: "http://api.test",
    tokenProvider: new NullAccessTokenProvider(),
    fetchImpl: fetchImpl as unknown as typeof fetch,
  });

  return { client, calls };
}

/** Always returns the same case detail for GET; fails any unexpected mutation. */
function readOnlyClient(detail: unknown) {
  return buildClient(() => ({ status: 200, body: detail }));
}

/**
 * Case-detail reads only.
 *
 * The page also embeds the Prompt 22 audit timeline, which issues its own GET
 * to `/timeline` through the same client. Excluding it keeps these assertions
 * measuring case-detail fetching and polling specifically.
 */
const getCalls = (calls: CallRecord[]) =>
  calls.filter(
    (call) => call.method === "GET" && !call.url.includes("/timeline"),
  );
const postCalls = (calls: CallRecord[], fragment: string) =>
  calls.filter((call) => call.method === "POST" && call.url.includes(fragment));

const renderCase = (client: ApiClient) =>
  render(<CaseDetailClient caseId={CASE_ID} apiClient={client} />);

/** Waits for the loaded header to appear. */
const findCaseHeading = () =>
  screen.findByRole("heading", { name: "Acme Learning", level: 1 });

// This file asserts state-driven control availability (RECOMMENDED shows
// Execute, AWAITING_APPROVAL shows Approve/Reject, etc.), not role gating —
// that's covered separately by case-presentation.test.ts and role.test.ts.
// Fix the role to ADMIN (permitted to execute and approve) so those
// assertions keep testing state, not an incidental default role.
const ORIGINAL_DEV_AUTH_TOKEN = process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;

beforeEach(() => {
  process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "dev-admin";
});

afterEach(() => {
  if (ORIGINAL_DEV_AUTH_TOKEN === undefined) {
    delete process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;
  } else {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = ORIGINAL_DEV_AUTH_TOKEN;
  }
});

describe("CaseDetailClient — loading, success, not found", () => {
  it("shows a header and section skeleton while loading", () => {
    const { client } = readOnlyClient(recommendedCaseFixture);
    const { container } = renderCase(client);

    expect(screen.getByText("Loading recovery case")).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByText("Acme Learning")).not.toBeInTheDocument();
  });

  it("renders the case header, status and context from the contract", async () => {
    const { client } = readOnlyClient(recommendedCaseFixture);
    renderCase(client);

    expect(await findCaseHeading()).toBeInTheDocument();
    expect(screen.getByLabelText("Status: Recommended")).toBeInTheDocument();
    expect(screen.getByText("High value")).toBeInTheDocument();
    expect(screen.getByText("Payment failure")).toBeInTheDocument();
    expect(screen.getByText("Source: Transaction")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  it("renders money values through the central formatter", async () => {
    const { client } = readOnlyClient(recommendedCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(screen.getAllByText(formatMoney(499900, "INR")).length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText(formatMoney(17800000, "INR")).length).toBeGreaterThan(
      0,
    );
    // Expected recovered and ERV come straight from the analysis payload.
    expect(screen.getAllByText(formatMoney(409918, "INR")).length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText(formatMoney(402500, "INR")).length).toBeGreaterThan(
      0,
    );
  });

  it("renders backend probability and confidence without recomputing them", async () => {
    const { client } = readOnlyClient(recommendedCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(screen.getAllByText("82.0%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("87.0%").length).toBeGreaterThan(0);
  });

  it("renders failure evidence without dumping raw JSON by default", async () => {
    const { client } = readOnlyClient(recommendedCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(screen.getByText("Payment rail downtime")).toBeInTheDocument();
    expect(screen.getByText("Upi")).toBeInTheDocument();
    // Evidence lives behind a disclosure rather than being expanded inline.
    expect(screen.getByText(/Provider evidence \(4\)/)).toBeInTheDocument();
  });

  it("renders the structured explanation and evidence factors", async () => {
    const { client } = readOnlyClient(recommendedCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(
      screen.getByText(
        "Alternative payment is preferred because the failed rail is degraded.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("UPI rail degradation is active")).toBeInTheDocument();
    expect(screen.getByText("Active upi downtime")).toBeInTheDocument();
    expect(screen.getByText("Probability is a model estimate, not a guarantee.")).toBeInTheDocument();
  });

  it("shows a clean not-found state for 404", async () => {
    const { client } = buildClient(() => ({
      status: 404,
      body: {
        error: { code: "CASE_NOT_FOUND", message: "Case not found." },
      },
    }));
    renderCase(client);

    expect(
      await screen.findByText("Case not found or unavailable"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a localized error with retry for a server failure", async () => {
    let failNext = true;
    const { client } = buildClient(() => {
      if (failNext) {
        failNext = false;
        return {
          status: 500,
          body: {
            error: {
              code: "INTERNAL_ERROR",
              message: "Traceback (most recent call last): psycopg2.Error",
              request_id: "req_case_1",
            },
          },
        };
      }
      return { status: 200, body: recommendedCaseFixture };
    });
    renderCase(client);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Reference: req_case_1")).toBeInTheDocument();
    // Raw backend internals must never reach the UI.
    expect(alert.textContent).not.toContain("Traceback");
    expect(alert.textContent).not.toContain("psycopg2");

    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await findCaseHeading()).toBeInTheDocument();
  });
});

describe("CaseDetailClient — state-aware controls", () => {
  it("offers Analyze only in DETECTED", async () => {
    const { client } = readOnlyClient(detectedCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(screen.getByRole("button", { name: "Analyze case" })).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "Execute recovery" }),
    ).not.toBeInTheDocument();
  });

  it("offers Execute only in RECOMMENDED", async () => {
    const { client } = readOnlyClient(recommendedCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(screen.getByRole("button", { name: "Execute recovery" })).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "Analyze case" }),
    ).not.toBeInTheDocument();
  });

  it("offers Approve and Reject in AWAITING_APPROVAL and explains server authority", async () => {
    const { client } = readOnlyClient(awaitingApprovalCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(screen.getByRole("button", { name: "Approve action" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reject action" })).toBeInTheDocument();
    expect(
      screen.getByText(/Approval is authorized by the backend/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Execute recovery" }),
    ).not.toBeInTheDocument();
  });

  it("hides Execute for an ANALYST and explains why instead of hiding silently", async () => {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "dev-analyst";
    const { client } = readOnlyClient(recommendedCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(
      screen.queryByRole("button", { name: "Execute recovery" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/your role cannot execute recovery actions/),
    ).toBeInTheDocument();
  });

  it("offers Execute for an OPERATOR, who cannot approve/reject", async () => {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "dev-operator";
    const { client } = readOnlyClient(awaitingApprovalCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(
      screen.queryByRole("button", { name: "Approve action" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reject action" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Only an admin can approve or reject this action/),
    ).toBeInTheDocument();
  });

  it("requires a rejection reason before Reject is enabled", async () => {
    const { client } = readOnlyClient(awaitingApprovalCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(screen.getByRole("button", { name: "Reject action" })).toBeDisabled();

    fireEvent.change(
      screen.getByLabelText("Rejection reason (required to reject)"),
      { target: { value: "Prefer manual handling" } },
    );

    expect(screen.getByRole("button", { name: "Reject action" })).toBeEnabled();
  });

  it("shows the scheduled time and no execute control in SCHEDULED", async () => {
    const { client } = readOnlyClient(scheduledCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(screen.getByText(/Scheduled for/)).toBeInTheDocument();
    expect(screen.getByText("30 Aug 2026, 12:00 UTC")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Execute recovery" }),
    ).not.toBeInTheDocument();
  });

  it("disables controls while EXECUTING", async () => {
    const { client } = readOnlyClient(executingCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(
      screen.getByText(/An action is currently executing/),
    ).toBeInTheDocument();
    for (const label of [
      "Execute recovery",
      "Analyze case",
      "Approve action",
      "Reject action",
    ]) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
  });

  it("blocks execution when the backend marks the selected action policy-ineligible", async () => {
    const blockedAnalysis = {
      ...recommendedCaseFixture.analysis!,
      selected_action: "RETRY_SAME_METHOD",
    };
    const { client } = readOnlyClient({
      ...recommendedCaseFixture,
      analysis: blockedAnalysis,
    });
    renderCase(client);
    await findCaseHeading();

    expect(screen.getByRole("button", { name: "Execute recovery" })).toBeDisabled();
    expect(screen.getByText("Blocked by policy")).toBeInTheDocument();
    // The reason text comes from the backend policy_reasons array.
    expect(
      screen.getAllByText(/Active payment rail downtime/).length,
    ).toBeGreaterThan(0);
  });

  it("keeps blocked candidates visible with their backend reasons", async () => {
    const { client } = readOnlyClient(recommendedCaseFixture);
    renderCase(client);
    await findCaseHeading();

    const row = screen.getByRole("row", { name: /Retry same method/ });
    expect(within(row).getByText(/Blocked/)).toBeInTheDocument();
    expect(within(row).getByText(formatMoney(121000, "INR"))).toBeInTheDocument();
    expect(within(row).getByText("31.0%")).toBeInTheDocument();
  });
});

describe("CaseDetailClient — terminal states", () => {
  it("renders the recovered module with authoritative outcome values", async () => {
    const { client } = readOnlyClient(recoveredCaseFixture);
    renderCase(client);
    await findCaseHeading();

    // Scoped to the outcome card, since the status badge also reads "Recovered".
    const outcome = screen.getByRole("region", { name: "Outcome" });
    expect(within(outcome).getByText("Recovered")).toBeInTheDocument();
    expect(
      within(outcome).getAllByText(formatMoney(499900, "INR")).length,
    ).toBeGreaterThan(0);
    expect(
      within(outcome).getByText(/Verified via Razorpay webhook/),
    ).toBeInTheDocument();
    expect(within(outcome).getByText("52m")).toBeInTheDocument();
    expect(within(outcome).getByText("pay_TESTRECOVERED")).toBeInTheDocument();
  });

  it.each([
    ["FAILED", failedCaseFixture, "Not recovered"],
    ["STOPPED", stoppedCaseFixture, "Stopped"],
  ])("renders the %s terminal state with no controls", async (status, fixture, headline) => {
    const { client } = readOnlyClient(fixture);
    renderCase(client);
    await findCaseHeading();

    const outcome = screen.getByRole("region", { name: "Outcome" });
    expect(within(outcome).getByText(headline)).toBeInTheDocument();
    expect(
      screen.getByText(`This case is in the terminal state ${status}. No recovery actions are available.`),
    ).toBeInTheDocument();
    for (const label of ["Execute recovery", "Analyze case", "Approve action"]) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
  });

  it("degrades cleanly when a terminal case has no outcome record", async () => {
    const { client } = readOnlyClient(failedCaseFixture);
    renderCase(client);
    await findCaseHeading();

    expect(
      screen.getByText("No outcome record is available for this case."),
    ).toBeInTheDocument();
  });
});

describe("CaseDetailClient — mutations", () => {
  it("submits the documented analyze request and refetches authoritative state", async () => {
    const { client, calls } = buildClient((call) => {
      if (call.method === "POST") {
        return { status: 200, body: { case_id: CASE_ID, status: "RECOMMENDED" } };
      }
      return {
        status: 200,
        body: calls.some((c) => c.method === "POST")
          ? recommendedCaseFixture
          : detectedCaseFixture,
      };
    });
    renderCase(client);
    await findCaseHeading();

    fireEvent.click(screen.getByRole("button", { name: "Analyze case" }));

    await waitFor(() => {
      expect(postCalls(calls, "/analyze")).toHaveLength(1);
    });
    expect(postCalls(calls, "/analyze")[0].body).toEqual({
      reason: "MANUAL_ANALYSIS",
    });

    // Authoritative refetch after success.
    await waitFor(() => {
      expect(getCalls(calls).length).toBeGreaterThanOrEqual(2);
    });
    expect(
      await screen.findByRole("button", { name: "Execute recovery" }),
    ).toBeInTheDocument();
  });

  it("submits the documented execute request and renders the refetched state", async () => {
    const { client, calls } = buildClient((call) => {
      if (call.method === "POST") {
        return {
          status: 201,
          body: {
            action: {
              id: ACTION_ID,
              action_type: "REQUEST_ALTERNATE_PAYMENT_METHOD",
              status: "SUCCEEDED",
              requires_approval: false,
              provider_reference: "plink_TESTREF123",
              scheduled_for: null,
            },
            case_status: "EXECUTING",
            customer_action: null,
          },
        };
      }
      return {
        status: 200,
        body: calls.some((c) => c.method === "POST")
          ? executingCaseFixture
          : recommendedCaseFixture,
      };
    });
    renderCase(client);
    await findCaseHeading();

    fireEvent.click(screen.getByRole("button", { name: "Execute recovery" }));

    await waitFor(() => {
      expect(postCalls(calls, "/actions")).toHaveLength(1);
    });
    // The frontend supplies only the analysis run and action type — never
    // amount, probability or ERV.
    expect(postCalls(calls, "/actions")[0].body).toEqual({
      analysis_run_id: ANALYSIS_RUN_ID,
      action_type: "REQUEST_ALTERNATE_PAYMENT_METHOD",
    });

    expect(
      await screen.findByText(/An action is currently executing/),
    ).toBeInTheDocument();
  });

  it("submits approve with the expected case version", async () => {
    const { client, calls } = buildClient((call) => {
      if (call.method === "POST") {
        return {
          status: 200,
          body: {
            action_id: ACTION_ID,
            action_status: "SUCCEEDED",
            case_status: "WAITING_FOR_OUTCOME",
          },
        };
      }
      return { status: 200, body: awaitingApprovalCaseFixture };
    });
    renderCase(client);
    await findCaseHeading();

    fireEvent.click(screen.getByRole("button", { name: "Approve action" }));

    await waitFor(() => {
      expect(postCalls(calls, "/approve")).toHaveLength(1);
    });
    expect(postCalls(calls, "/approve")[0].body).toEqual({
      expected_case_version: 4,
    });
    expect(postCalls(calls, "/approve")[0].url).toContain(ACTION_ID);
  });

  it("shows the payment link after approval, even though the approve response never carries it", async () => {
    // ApproveRecoveryActionResponse has no customer_action field -- the link
    // can only reach the UI through a case-detail refetch. This proves the
    // panel picks it up from latest_action.customer_action after the
    // post-approve refetch, not just from the immediate-execute response.
    const { client, calls } = buildClient((call) => {
      if (call.method === "POST") {
        return {
          status: 200,
          body: {
            action_id: ACTION_ID,
            action_status: "SUCCEEDED",
            case_status: "WAITING_FOR_OUTCOME",
          },
        };
      }
      const approved = calls.some((c) => c.method === "POST");
      return {
        status: 200,
        body: approved
          ? makeCase({
              status: "WAITING_FOR_OUTCOME",
              latestAction: approvedActionWithLinkFixture,
            })
          : awaitingApprovalCaseFixture,
      };
    });
    renderCase(client);
    await findCaseHeading();

    expect(
      screen.queryByText("https://rzp.io/i/approvedlink"),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve action" }));

    const link = await screen.findByText("https://rzp.io/i/approvedlink");
    expect(link).toHaveAttribute("href", "https://rzp.io/i/approvedlink");
  });

  it("submits reject with the operator reason and reanalyze flag", async () => {
    const { client, calls } = buildClient((call) => {
      if (call.method === "POST") {
        return {
          status: 200,
          body: {
            action_id: ACTION_ID,
            action_status: "CANCELLED",
            case_status: "ANALYZING",
          },
        };
      }
      return { status: 200, body: awaitingApprovalCaseFixture };
    });
    renderCase(client);
    await findCaseHeading();

    fireEvent.change(
      screen.getByLabelText("Rejection reason (required to reject)"),
      { target: { value: "Prefer manual handling" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Reject action" }));

    await waitFor(() => {
      expect(postCalls(calls, "/reject")).toHaveLength(1);
    });
    expect(postCalls(calls, "/reject")[0].body).toEqual({
      reason: "Prefer manual handling",
      reanalyze: true,
    });
  });

  it("prevents duplicate submission while a mutation is pending", async () => {
    let releasePost!: () => void;
    const postGate = new Promise<void>((resolve) => {
      releasePost = resolve;
    });

    const calls: CallRecord[] = [];
    const fetchImpl = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const method = (init?.method ?? "GET").toUpperCase();
        calls.push({ url: String(input), method, body: null });
        if (method === "POST") {
          await postGate;
          return jsonResponse({
            status: 201,
            body: {
              action: {
                id: ACTION_ID,
                action_type: "REQUEST_ALTERNATE_PAYMENT_METHOD",
                status: "SUCCEEDED",
                requires_approval: false,
                provider_reference: null,
                scheduled_for: null,
              },
              case_status: "EXECUTING",
              customer_action: null,
            },
          });
        }
        return jsonResponse({ status: 200, body: recommendedCaseFixture });
      },
    );

    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokenProvider: new NullAccessTokenProvider(),
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    renderCase(client);
    await findCaseHeading();

    const button = screen.getByRole("button", { name: "Execute recovery" });
    fireEvent.click(button);

    const pending = await screen.findByRole("button", { name: "Submitting…" });
    expect(pending).toBeDisabled();
    expect(pending).toHaveAttribute("aria-busy", "true");

    // Further clicks while pending must not produce another request.
    fireEvent.click(pending);
    fireEvent.click(pending);

    await act(async () => {
      releasePost();
      await postGate;
    });

    await waitFor(() => {
      expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);
    });
  });
});

describe("CaseDetailClient — 409 stale conflict", () => {
  it("refetches authoritative state, warns the user, and does not retry the mutation", async () => {
    const calls: CallRecord[] = [];
    const { client } = buildClient((call) => {
      calls.push(call);
      if (call.method === "POST") {
        return {
          status: 409,
          body: {
            error: {
              code: "STALE_CASE_VERSION",
              message: "Case version changed.",
              request_id: "req_conflict_1",
            },
          },
        };
      }
      // After the conflict the server reports the newer state.
      return {
        status: 200,
        body: calls.some((c) => c.method === "POST")
          ? recoveredCaseFixture
          : awaitingApprovalCaseFixture,
      };
    });

    renderCase(client);
    await findCaseHeading();
    expect(screen.getByRole("button", { name: "Approve action" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Approve action" }));

    // 1. The user is told the case changed.
    expect(await screen.findByText("This case changed")).toBeInTheDocument();

    // 2. Updated server state replaces the stale UI.
    await waitFor(() => {
      expect(screen.getByLabelText("Status: Recovered")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: "Approve action" }),
    ).not.toBeInTheDocument();

    // 3. The mutation was attempted exactly once — never auto-retried.
    expect(postCalls(calls, "/approve")).toHaveLength(1);

    // 4. A refetch followed the conflict.
    expect(getCalls(calls).length).toBeGreaterThanOrEqual(2);
  });

  it("offers no retry button for a failed mutation", async () => {
    const { client } = buildClient((call) => {
      if (call.method === "POST") {
        return {
          status: 409,
          body: {
            error: { code: "INVALID_CASE_STATE", message: "Bad state." },
          },
        };
      }
      return { status: 200, body: awaitingApprovalCaseFixture };
    });

    renderCase(client);
    await findCaseHeading();
    fireEvent.click(screen.getByRole("button", { name: "Approve action" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
  });

  it("shows a safe mapped message for a policy rejection without leaking internals", async () => {
    const { client } = buildClient((call) => {
      if (call.method === "POST") {
        return {
          status: 422,
          body: {
            error: {
              code: "ACTION_BLOCKED_BY_POLICY",
              message: "Blocked.",
              request_id: "req_policy_1",
            },
          },
        };
      }
      return { status: 200, body: recommendedCaseFixture };
    });

    renderCase(client);
    await findCaseHeading();
    fireEvent.click(screen.getByRole("button", { name: "Execute recovery" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Action blocked by policy")).toBeInTheDocument();
    // A policy rejection is not a conflict, so no stale-case banner is shown.
    expect(screen.queryByText("This case changed")).not.toBeInTheDocument();
  });
});

describe("CaseDetailClient — WAITING_FOR_OUTCOME polling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** Flushes pending timers and promises inside act, avoiding act warnings. */
  const advance = async (ms: number) => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  };

  it("polls the read endpoint on a bounded 4 second schedule", async () => {
    const { client, calls } = readOnlyClient(waitingForOutcomeCaseFixture);
    renderCase(client);
    await advance(0);

    expect(screen.getByText("plink_TESTREF123")).toBeInTheDocument();
    expect(getCalls(calls)).toHaveLength(1);

    await advance(4000);
    expect(getCalls(calls)).toHaveLength(2);

    await advance(4000);
    expect(getCalls(calls)).toHaveLength(3);
  });

  it("does not poll faster than the configured interval", async () => {
    const { client, calls } = readOnlyClient(waitingForOutcomeCaseFixture);
    renderCase(client);
    await advance(0);

    await advance(3000);
    expect(getCalls(calls)).toHaveLength(1);
  });

  it("stops polling once the state moves away from WAITING_FOR_OUTCOME", async () => {
    let recovered = false;
    const { client, calls } = buildClient(() => {
      const body = recovered ? recoveredCaseFixture : waitingForOutcomeCaseFixture;
      return { status: 200, body };
    });

    renderCase(client);
    await advance(0);
    expect(getCalls(calls)).toHaveLength(1);

    recovered = true;
    await advance(4000);
    expect(getCalls(calls)).toHaveLength(2);
    expect(screen.getByLabelText("Status: Recovered")).toBeInTheDocument();

    // No further polling after the terminal state arrives.
    await advance(20000);
    expect(getCalls(calls)).toHaveLength(2);
  });

  it("stops polling after the bounded attempt budget is exhausted", async () => {
    const { client, calls } = readOnlyClient(waitingForOutcomeCaseFixture);
    renderCase(client);
    await advance(0);

    // Each poll schedules the next one from an effect, so advance tick by tick.
    // 15 attempts is the documented ceiling: 1 initial load + 15 polls.
    for (let tick = 0; tick < 20; tick += 1) {
      await advance(4000);
    }
    expect(getCalls(calls)).toHaveLength(16);

    for (let tick = 0; tick < 5; tick += 1) {
      await advance(4000);
    }
    expect(getCalls(calls)).toHaveLength(16);
    expect(
      screen.getByText(/Automatic status checks have stopped/),
    ).toBeInTheDocument();
  });

  it("stops polling when the component unmounts", async () => {
    const { client, calls } = readOnlyClient(waitingForOutcomeCaseFixture);
    const { unmount } = renderCase(client);
    await advance(0);
    expect(getCalls(calls)).toHaveLength(1);

    unmount();
    await advance(4000 * 3);
    expect(getCalls(calls)).toHaveLength(1);
  });

  it("keeps a manual Refresh status control available", async () => {
    const { client, calls } = readOnlyClient(waitingForOutcomeCaseFixture);
    renderCase(client);
    await advance(0);

    fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));
    await advance(0);

    expect(getCalls(calls).length).toBeGreaterThanOrEqual(2);
  });
});
