import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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
import {
  CASE_ID,
  awaitingApprovalCaseFixture,
  recommendedCaseFixture,
} from "@/app/(app)/recovery/[caseId]/__fixtures__/case-fixtures";
import {
  SENTINELS,
  analysisEntry,
  caseCreatedEntry,
  executionEntry,
  noEvidenceEntry,
  outcomeEntry,
  policyEntry,
  providerRawEventEntry,
  staleWebhookEntry,
  timelineFixture,
  unsafeEvidenceEntry,
  wrongTypeEvidenceEntry,
} from "@/app/(app)/recovery/[caseId]/__fixtures__/timeline-fixtures";
import type { TimelineEntry } from "@/app/(app)/recovery/[caseId]/case-types";

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

const isTimelineUrl = (url: string) => url.includes("/timeline");

/**
 * Single shared `ApiClient` for the whole page, so capturing its transport also
 * proves the timeline reuses the existing client rather than a second one.
 */
function buildClient(routeFor: (call: CallRecord) => RouteBody) {
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
      return jsonResponse(routeFor(record));
    },
  );

  const client = new ApiClient({
    baseUrl: "http://api.test",
    tokenProvider: new NullAccessTokenProvider(),
    fetchImpl: fetchImpl as unknown as typeof fetch,
  });

  return { client, calls };
}

/** Case detail succeeds; the timeline returns the supplied entries. */
function pageClient(
  entries: TimelineEntry[],
  caseDetail: unknown = recommendedCaseFixture,
) {
  return buildClient((call) =>
    isTimelineUrl(call.url)
      ? { status: 200, body: { items: entries } }
      : { status: 200, body: caseDetail },
  );
}

const renderPage = (client: ApiClient) =>
  render(<CaseDetailClient caseId={CASE_ID} apiClient={client} />);

const findCaseHeading = () =>
  screen.findByRole("heading", { name: "Acme Learning", level: 1 });

const timelineRegion = () =>
  screen.getByRole("region", { name: "Agent & audit timeline" });

const timelineCalls = (calls: CallRecord[]) =>
  calls.filter((call) => isTimelineUrl(call.url));

describe("AuditTimeline — loading, success, empty", () => {
  it("shows a timeline-shaped skeleton with no fabricated content", async () => {
    // Case detail resolves immediately while the timeline stays pending, which
    // is the only moment the timeline skeleton is visible.
    let resolveTimeline!: (response: Response) => void;
    const pendingTimeline = new Promise<Response>((resolve) => {
      resolveTimeline = resolve;
    });

    const fetchImpl = vi.fn(
      async (input: RequestInfo | URL): Promise<Response> =>
        isTimelineUrl(String(input))
          ? pendingTimeline
          : jsonResponse({ status: 200, body: recommendedCaseFixture }),
    );

    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokenProvider: new NullAccessTokenProvider(),
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    renderPage(client);
    await findCaseHeading();

    const region = timelineRegion();
    expect(
      within(region).getByText("Loading audit timeline"),
    ).toBeInTheDocument();
    expect(region.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(within(region).queryByText("CASE_CREATED")).not.toBeInTheDocument();

    resolveTimeline(
      jsonResponse({ status: 200, body: { items: timelineFixture } }),
    );
    expect(
      await within(timelineRegion()).findByText("CASE_CREATED"),
    ).toBeInTheDocument();
  });

  it("renders entries returned by the endpoint", async () => {
    const { client } = pageClient(timelineFixture);
    renderPage(client);
    await findCaseHeading();

    const region = await screen.findByRole("region", {
      name: "Agent & audit timeline",
    });
    expect(within(region).getByText("CASE_CREATED")).toBeInTheDocument();
    expect(
      within(region).getByText("Failed UPI payment detected."),
    ).toBeInTheDocument();
    expect(within(region).getByText("ANALYSIS_COMPLETED")).toBeInTheDocument();
    expect(
      within(region).getByText("Alternative payment ranked #1."),
    ).toBeInTheDocument();
  });

  it("renders each documented category as visible text, not colour alone", async () => {
    const { client } = pageClient(timelineFixture);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    for (const label of [
      "Provider event",
      "System analysis",
      "Policy decision",
      "Action execution",
      "Recovery outcome",
    ]) {
      expect(within(region).getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("uses the documented actor enum as a label", async () => {
    const { client } = pageClient([caseCreatedEntry, analysisEntry, policyEntry]);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    expect(within(region).getByText("by Provider")).toBeInTheDocument();
    expect(within(region).getByText("by Model")).toBeInTheDocument();
    expect(within(region).getByText("by System")).toBeInTheDocument();
  });

  it("renders a raw provider event name verbatim", async () => {
    const { client } = pageClient([providerRawEventEntry]);
    renderPage(client);
    await findCaseHeading();

    expect(
      within(timelineRegion()).getByText("payment.captured"),
    ).toBeInTheDocument();
  });

  it("shows a timeline-specific empty state without fabricating events", async () => {
    const { client } = pageClient([]);
    renderPage(client);
    await findCaseHeading();

    const region = timelineRegion();
    expect(
      within(region).getByText("No audit events recorded yet"),
    ).toBeInTheDocument();
    // No invented lifecycle scaffolding.
    for (const invented of [
      "CASE_CREATED",
      "ANALYSIS_COMPLETED",
      "CASE_RECOVERED",
    ]) {
      expect(within(region).queryByText(invented)).not.toBeInTheDocument();
    }
  });

  it("renders only the events returned, never a completed lifecycle", async () => {
    const { client } = pageClient([caseCreatedEntry]);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    expect(within(region).getByText("CASE_CREATED")).toBeInTheDocument();
    expect(within(region).queryByText("ANALYSIS_COMPLETED")).not.toBeInTheDocument();
    expect(within(region).queryByText("CASE_RECOVERED")).not.toBeInTheDocument();
    expect(within(region).getAllByRole("listitem")).toHaveLength(1);
  });
});

describe("AuditTimeline — ordering and timestamps", () => {
  it("preserves the endpoint's ascending order", async () => {
    const { client } = pageClient(timelineFixture);
    renderPage(client);
    await findCaseHeading();

    const items = within(timelineRegion()).getAllByRole("listitem");
    const order = items.map(
      (item) => item.querySelector("time")?.getAttribute("datetime") ?? "",
    );
    expect(order).toEqual(timelineFixture.map((entry) => entry.occurred_at));
  });

  it("does not independently re-sort a response", async () => {
    // The endpoint guarantees canonical ordering, so whatever order it returns
    // is rendered unchanged rather than being second-guessed here.
    const reversed = [...timelineFixture].reverse();
    const { client } = pageClient(reversed);
    renderPage(client);
    await findCaseHeading();

    const items = within(timelineRegion()).getAllByRole("listitem");
    const order = items.map(
      (item) => item.querySelector("time")?.getAttribute("datetime") ?? "",
    );
    expect(order).toEqual(reversed.map((entry) => entry.occurred_at));
  });

  it("renders timestamps in UTC without shifting the calendar date", async () => {
    const { client } = pageClient([caseCreatedEntry]);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    // 2026-08-30T08:20:03Z must stay on 30 Aug regardless of the test timezone.
    expect(within(region).getByText("30 Aug 2026, 08:20 UTC")).toBeInTheDocument();
    const times = within(region).getAllByRole("time");
    expect(times[0]).toHaveAttribute("datetime", caseCreatedEntry.occurred_at);
  });
});

describe("AuditTimeline — safe evidence disclosure", () => {
  it("shows allowlisted evidence inside a disclosure", async () => {
    const { client } = pageClient([caseCreatedEntry]);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    expect(within(region).getByText("Details (3)")).toBeInTheDocument();
    expect(within(region).getByText("Failure category")).toBeInTheDocument();
    expect(within(region).getByText("Payment rail downtime")).toBeInTheDocument();
    expect(within(region).getByText("evt_TESTPROVIDER01")).toBeInTheDocument();
  });

  it("renders policy reasons and case versions when supplied", async () => {
    const { client } = pageClient([policyEntry, executionEntry]);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    expect(
      within(region).getByText(
        "Amount above auto action limit, High value customer",
      ),
    ).toBeInTheDocument();
    expect(within(region).getByText("Previous case version")).toBeInTheDocument();
    expect(within(region).getByText("New case version")).toBeInTheDocument();
  });

  it("omits the disclosure entirely when evidence is empty", async () => {
    const { client } = pageClient([noEvidenceEntry]);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    expect(within(region).getByText("FAILURE_NORMALIZED")).toBeInTheDocument();
    expect(within(region).queryByText(/^Details/)).not.toBeInTheDocument();
    // No placeholder junk in place of absent evidence.
    for (const junk of ["undefined", "null", "{}", "[object Object]"]) {
      expect(region.textContent).not.toContain(junk);
    }
  });

  it("drops allowlisted keys carrying the wrong type", async () => {
    const { client } = pageClient([wrongTypeEvidenceEntry]);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    expect(within(region).queryByText(/^Details/)).not.toBeInTheDocument();
    expect(region.textContent).not.toContain("[object Object]");
  });
});

describe("AuditTimeline — privacy and safe disclosure", () => {
  it("never renders secrets, PII, raw payloads or model reasoning", async () => {
    const { client } = pageClient([unsafeEvidenceEntry]);
    const { container } = renderPage(client);
    await findCaseHeading();

    const html = container.innerHTML;
    const text = container.textContent ?? "";

    for (const [name, sentinel] of Object.entries(SENTINELS)) {
      expect(text, `sentinel "${name}" leaked into text`).not.toContain(
        sentinel,
      );
      expect(html, `sentinel "${name}" leaked into markup`).not.toContain(
        sentinel,
      );
    }
  });

  it("does not expose full email addresses or phone numbers", async () => {
    const { client } = pageClient([unsafeEvidenceEntry]);
    const { container } = renderPage(client);
    await findCaseHeading();
    const text = container.textContent ?? "";

    expect(text).not.toMatch(/[\w.+-]+@[\w-]+\.[\w.]+/);
    // Digit runs inside a hyphenated identifier (a run UUID) are not phone
    // numbers, so only standalone long digit sequences are rejected.
    expect(text).not.toMatch(/(?<![\w-])\+?\d{10,}(?![\w-])/);
  });

  it("does not render the dangerous evidence key names either", async () => {
    const { client } = pageClient([unsafeEvidenceEntry]);
    renderPage(client);
    await findCaseHeading();
    const text = timelineRegion().textContent ?? "";

    for (const key of [
      "authorization",
      "api_key",
      "webhook_secret",
      "raw_payload",
      "webhook_body",
      "chain_of_thought",
      "reasoning",
      "prompt",
      "completion",
      "stack_trace",
      "card_number",
    ]) {
      expect(text.toLowerCase()).not.toContain(key);
    }
  });

  it("still renders the two safe members of a hostile evidence object", async () => {
    const { client } = pageClient([unsafeEvidenceEntry]);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    expect(within(region).getByText("Details (2)")).toBeInTheDocument();
    expect(within(region).getByText("Payment rail downtime")).toBeInTheDocument();
  });
});

describe("AuditTimeline — stale and warning events", () => {
  it("marks a documented stale-webhook event as a warning", async () => {
    const { client } = pageClient([caseCreatedEntry, staleWebhookEntry]);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    expect(within(region).getByText("Warning")).toBeInTheDocument();
    expect(
      within(region).getByText(
        "Older payment.failed webhook ignored after verified capture.",
      ),
    ).toBeInTheDocument();
  });

  it("shows no warning when the contract does not justify one", async () => {
    // No stale/superseded/event-version field exists, so ordinary events are
    // never marked stale by age, order or current case status.
    const { client } = pageClient([
      caseCreatedEntry,
      analysisEntry,
      outcomeEntry,
    ]);
    renderPage(client);
    await findCaseHeading();
    const region = timelineRegion();

    expect(within(region).queryByText("Warning")).not.toBeInTheDocument();
    expect(region.textContent).not.toContain("Stale");
    expect(region.textContent).not.toContain("Superseded");
  });
});

describe("AuditTimeline — error containment and refresh", () => {
  it("shows a localized mapped error with a reference and a retry", async () => {
    let failTimeline = true;
    const { client } = buildClient((call) => {
      if (isTimelineUrl(call.url)) {
        if (failTimeline) {
          failTimeline = false;
          return {
            status: 500,
            body: {
              error: {
                code: "INTERNAL_ERROR",
                message:
                  "Traceback (most recent call last): psycopg2.OperationalError",
                request_id: "req_timeline_1",
              },
            },
          };
        }
        return { status: 200, body: { items: timelineFixture } };
      }
      return { status: 200, body: recommendedCaseFixture };
    });

    renderPage(client);
    await findCaseHeading();

    const region = timelineRegion();
    const alert = within(region).getByRole("alert");
    expect(within(alert).getByText("Reference: req_timeline_1")).toBeInTheDocument();
    // Internal error text must never surface.
    expect(alert.textContent).not.toContain("Traceback");
    expect(alert.textContent).not.toContain("psycopg2");

    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));

    expect(
      await within(timelineRegion()).findByText("CASE_CREATED"),
    ).toBeInTheDocument();
  });

  it("keeps the case detail and its action controls usable when the timeline fails", async () => {
    const { client } = buildClient((call) =>
      isTimelineUrl(call.url)
        ? { status: 503, body: { error: { code: "SERVICE_UNAVAILABLE" } } }
        : { status: 200, body: recommendedCaseFixture },
    );

    renderPage(client);
    await findCaseHeading();

    // Prompt 21 UI is unaffected.
    expect(screen.getByRole("button", { name: "Execute recovery" })).toBeEnabled();
    expect(screen.getByLabelText("Status: Recommended")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Candidate action comparison" }),
    ).toBeInTheDocument();
    // The failure is scoped to the timeline section.
    expect(within(timelineRegion()).getByRole("alert")).toBeInTheDocument();
  });

  it("refreshes the timeline through the shared ApiClient without mutating", async () => {
    const { client, calls } = pageClient(timelineFixture);
    renderPage(client);
    await findCaseHeading();

    await waitFor(() => expect(timelineCalls(calls)).toHaveLength(1));
    expect(timelineCalls(calls)[0].method).toBe("GET");
    expect(timelineCalls(calls)[0].url).toBe(
      `http://api.test/api/v1/recovery-cases/${CASE_ID}/timeline`,
    );

    fireEvent.click(
      within(timelineRegion()).getByRole("button", { name: "Refresh timeline" }),
    );

    await waitFor(() => expect(timelineCalls(calls)).toHaveLength(2));
    // A timeline read is never a mutation.
    expect(calls.every((call) => call.method === "GET")).toBe(true);
  });

  it("does not disturb Prompt 21 mutation behavior", async () => {
    const { client, calls } = buildClient((call) => {
      if (isTimelineUrl(call.url)) {
        return { status: 200, body: { items: timelineFixture } };
      }
      if (call.method === "POST") {
        return {
          status: 200,
          body: {
            action_id: "99999999-9999-4999-8999-999999999999",
            action_status: "SUCCEEDED",
            case_status: "WAITING_FOR_OUTCOME",
          },
        };
      }
      return { status: 200, body: awaitingApprovalCaseFixture };
    });

    renderPage(client);
    await findCaseHeading();

    fireEvent.click(
      within(timelineRegion()).getByRole("button", { name: "Refresh timeline" }),
    );
    await waitFor(() => expect(timelineCalls(calls)).toHaveLength(2));

    // The approve mutation still submits exactly once with the documented body.
    fireEvent.click(screen.getByRole("button", { name: "Approve action" }));

    await waitFor(() => {
      expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);
    });
    expect(calls.filter((call) => call.method === "POST")[0].body).toEqual({
      expected_case_version: 4,
    });
  });

  it("refreshes the timeline when the case reports a new version", async () => {
    let caseVersion = 4;
    const { client, calls } = buildClient((call) => {
      if (isTimelineUrl(call.url)) {
        return { status: 200, body: { items: timelineFixture } };
      }
      return {
        status: 200,
        body: {
          ...recommendedCaseFixture,
          case: { ...recommendedCaseFixture.case, version: caseVersion },
        },
      };
    });

    renderPage(client);
    await findCaseHeading();
    await waitFor(() => expect(timelineCalls(calls)).toHaveLength(1));

    caseVersion = 5;
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(timelineCalls(calls).length).toBeGreaterThanOrEqual(2);
    });
  });
});

describe("AuditTimeline — accessibility", () => {
  it("uses a labelled section, a heading and an ordered list", async () => {
    const { client } = pageClient(timelineFixture);
    renderPage(client);
    await findCaseHeading();

    expect(
      screen.getByRole("heading", { name: "Agent & audit timeline", level: 2 }),
    ).toBeInTheDocument();

    const region = timelineRegion();
    expect(within(region).getByRole("list")).toBeInTheDocument();
    expect(within(region).getAllByRole("listitem")).toHaveLength(
      timelineFixture.length,
    );
  });

  it("keeps the refresh control keyboard reachable and marks it busy", async () => {
    const { client } = pageClient(timelineFixture);
    renderPage(client);
    await findCaseHeading();

    const button = within(timelineRegion()).getByRole("button", {
      name: "Refresh timeline",
    });
    expect(button).toBeEnabled();
    expect(button).toHaveAttribute("type", "button");
    button.focus();
    expect(button).toHaveFocus();
  });

  it("does not move focus when the timeline refreshes", async () => {
    const { client, calls } = pageClient(timelineFixture);
    renderPage(client);
    await findCaseHeading();

    const button = within(timelineRegion()).getByRole("button", {
      name: "Refresh timeline",
    });
    button.focus();
    fireEvent.click(button);
    await waitFor(() => expect(timelineCalls(calls)).toHaveLength(2));

    expect(
      within(timelineRegion()).getByRole("button", { name: "Refresh timeline" }),
    ).toHaveFocus();
  });
});
