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

import { DashboardClient } from "@/app/(app)/dashboard/dashboard-client";
import {
  DASHBOARD_SUMMARY_PATH,
  TOP_OPPORTUNITIES_PATH,
} from "@/app/(app)/dashboard/use-dashboard-data";
import { ApiClient } from "@/lib/api/api-client";
import { NullAccessTokenProvider } from "@/lib/auth/token-provider";
import { formatMoney } from "@/lib/money/format-money";
import {
  dashboardSummaryFixture,
  emptyDashboardSummaryFixture,
  emptyTopOpportunitiesFixture,
  sparseDashboardSummaryFixture,
  topOpportunitiesFixture,
} from "@/app/(app)/dashboard/__fixtures__/dashboard-fixtures";

type RouteBody = { status: number; body: unknown };

function jsonResponse({ status, body }: RouteBody): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    text: async () => JSON.stringify(body),
  } as Response;
}

/**
 * Builds a client backed by the real transport so tests exercise the shared
 * ApiClient, its Bearer handling and its error-envelope parsing.
 */
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

function happyPathClient() {
  return buildClient((url) => {
    if (url.includes(DASHBOARD_SUMMARY_PATH)) {
      return { status: 200, body: dashboardSummaryFixture };
    }
    return { status: 200, body: topOpportunitiesFixture };
  });
}

describe("DashboardClient", () => {
  it("renders the dashboard from a representative API response", async () => {
    const { client } = happyPathClient();
    render(<DashboardClient apiClient={client} />);

    expect(
      await screen.findByRole("heading", { name: "Revenue Recovery Overview", level: 1 }),
    ).toBeInTheDocument();

    for (const sectionTitle of [
      "Recovery trend",
      "Action effectiveness",
      "Failure breakdown",
      "Top recovery opportunities",
    ]) {
      expect(
        await screen.findByRole("heading", { name: sectionTitle, level: 2 }),
      ).toBeInTheDocument();
    }

    expect(screen.getByText("Revenue at Risk")).toBeInTheDocument();
    expect(screen.getByText("Recovered Revenue")).toBeInTheDocument();
    expect(screen.getByText("Recovery Rate")).toBeInTheDocument();
    expect(screen.getByText("Incremental vs Baseline")).toBeInTheDocument();
  });

  it("requests the documented dashboard and recovery-case endpoints", async () => {
    const { client, fetchImpl } = happyPathClient();
    render(<DashboardClient apiClient={client} />);

    await screen.findByRole("heading", { name: "Recovery trend", level: 2 });

    const requestedUrls = fetchImpl.mock.calls.map(([input]) => String(input));
    expect(requestedUrls.some((url) => url.endsWith(DASHBOARD_SUMMARY_PATH))).toBe(true);
    expect(requestedUrls.some((url) => url.endsWith(TOP_OPPORTUNITIES_PATH))).toBe(true);
  });

  it("formats monetary KPIs with the centralized money formatter", async () => {
    const { client } = happyPathClient();
    render(<DashboardClient apiClient={client} />);

    const expectedAtRisk = formatMoney(
      dashboardSummaryFixture.revenue_at_risk_minor,
      dashboardSummaryFixture.currency,
    );
    const expectedRecovered = formatMoney(
      dashboardSummaryFixture.revenue_recovered_minor,
      dashboardSummaryFixture.currency,
    );
    const expectedIncremental = formatMoney(
      dashboardSummaryFixture.incremental_recovered_minor,
      dashboardSummaryFixture.currency,
    );

    expect(await screen.findByText(expectedAtRisk)).toBeInTheDocument();
    expect(screen.getByText(expectedRecovered)).toBeInTheDocument();
    expect(screen.getByText(expectedIncremental)).toBeInTheDocument();
  });

  it("shows the backend-supplied data source label", async () => {
    const { client } = happyPathClient();
    render(<DashboardClient apiClient={client} />);

    expect(
      await screen.findByText("Synthetic batch + Razorpay Test Mode"),
    ).toBeInTheDocument();
    expect(screen.getByText("Data source")).toBeInTheDocument();
  });

  it("shows an accessible skeleton while metrics load", async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });

    const { client } = buildClient(async (url) => {
      if (url.includes(DASHBOARD_SUMMARY_PATH)) {
        await gate;
      }
      return {
        status: 200,
        body: url.includes(DASHBOARD_SUMMARY_PATH)
          ? dashboardSummaryFixture
          : topOpportunitiesFixture,
      };
    });

    const { container } = render(<DashboardClient apiClient={client} />);

    expect(screen.getByText("Loading dashboard metrics")).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByText("Revenue at Risk")).not.toBeInTheDocument();

    release?.();
    expect(await screen.findByText("Revenue at Risk")).toBeInTheDocument();
    expect(screen.queryByText("Loading dashboard metrics")).not.toBeInTheDocument();
  });

  it("renders a localized error with retry and recovers on success", async () => {
    const { client } = buildClient((url, callIndex) => {
      if (url.includes(DASHBOARD_SUMMARY_PATH)) {
        if (callIndex === 0) {
          return {
            status: 500,
            body: {
              error: {
                code: "INTERNAL_ERROR",
                message: "Dashboard aggregation failed.",
                request_id: "req_dashboard_1",
              },
            },
          };
        }
        return { status: 200, body: dashboardSummaryFixture };
      }
      return { status: 200, body: topOpportunitiesFixture };
    });

    render(<DashboardClient apiClient={client} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(
      screen.getByText(/Dashboard metrics are temporarily unavailable/),
    ).toBeInTheDocument();
    expect(within(alert).getByText("Reference: req_dashboard_1")).toBeInTheDocument();
    // The page heading stays mounted so the failure remains localized.
    expect(
      screen.getByRole("heading", { name: "Revenue Recovery Overview", level: 1 }),
    ).toBeInTheDocument();

    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Revenue at Risk")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("never leaks raw backend internals into the error message", async () => {
    const { client } = buildClient((url) => {
      if (url.includes(DASHBOARD_SUMMARY_PATH)) {
        return {
          status: 500,
          body: {
            error: {
              code: "INTERNAL_ERROR",
              message: "Traceback (most recent call last): psycopg2.OperationalError",
              request_id: "req_dashboard_2",
            },
          },
        };
      }
      return { status: 200, body: topOpportunitiesFixture };
    });

    render(<DashboardClient apiClient={client} />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).not.toContain("Traceback");
    expect(alert.textContent).not.toContain("psycopg2");
  });

  it("renders the empty state without inventing metrics", async () => {
    const { client } = buildClient((url) => ({
      status: 200,
      body: url.includes(DASHBOARD_SUMMARY_PATH)
        ? emptyDashboardSummaryFixture
        : emptyTopOpportunitiesFixture,
    }));

    render(<DashboardClient apiClient={client} />);

    expect(await screen.findByText("No recovery activity yet")).toBeInTheDocument();
    expect(screen.getByText(/Seed demo data/)).toBeInTheDocument();
    expect(screen.queryByText("Revenue at Risk")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders top opportunities with a link to the case detail route", async () => {
    const { client } = happyPathClient();
    render(<DashboardClient apiClient={client} />);

    const table = await screen.findByRole("table");
    expect(within(table).getByText("Acme Learning")).toBeInTheDocument();

    const row = screen.getByRole("row", { name: /Acme Learning/ });
    expect(
      within(row).getByText(formatMoney(499900, "INR")),
    ).toBeInTheDocument();
    expect(within(row).getByText("Recommended")).toBeInTheDocument();

    const link = within(row).getByRole("link", { name: /View case/ });
    expect(link).toHaveAttribute(
      "href",
      "/recovery/11111111-1111-4111-8111-111111111111",
    );
  });

  it("shows a dash instead of inventing values for null contract fields", async () => {
    const { client } = buildClient((url) => ({
      status: 200,
      body: url.includes(DASHBOARD_SUMMARY_PATH)
        ? sparseDashboardSummaryFixture
        : topOpportunitiesFixture,
    }));

    render(<DashboardClient apiClient={client} />);

    await screen.findByText("Avg. time to recover");
    const averageStat = screen.getByText("Avg. time to recover").parentElement;
    expect(averageStat).not.toBeNull();
    expect(within(averageStat as HTMLElement).getByText("—")).toBeInTheDocument();

    const unscoredRow = screen.getByRole("row", { name: /Northwind/ });
    expect(within(unscoredRow).getAllByText("—")).toHaveLength(2);
  });

  it("keeps sections that have no rows honest instead of hiding them", async () => {
    const { client } = buildClient((url) => ({
      status: 200,
      body: url.includes(DASHBOARD_SUMMARY_PATH)
        ? sparseDashboardSummaryFixture
        : topOpportunitiesFixture,
    }));

    render(<DashboardClient apiClient={client} />);

    expect(
      await screen.findByText("No recovery actions have completed yet."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No failure categories have been reported yet."),
    ).toBeInTheDocument();
  });

  it("degrades only the opportunities section when the case list fails", async () => {
    const { client } = buildClient((url) => {
      if (url.includes(DASHBOARD_SUMMARY_PATH)) {
        return { status: 200, body: dashboardSummaryFixture };
      }
      return {
        status: 503,
        body: { error: { code: "SERVICE_UNAVAILABLE", message: "unavailable" } },
      };
    });

    render(<DashboardClient apiClient={client} />);

    expect(await screen.findByText("Revenue at Risk")).toBeInTheDocument();
    expect(
      screen.getByText(/Recovery cases could not be loaded right now/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("exposes accessible chart and table semantics", async () => {
    const { client } = happyPathClient();
    render(<DashboardClient apiClient={client} />);

    await screen.findByRole("heading", { name: "Recovery trend", level: 2 });

    expect(
      screen.getByRole("img", { name: /Recovery trend across 3 reporting days/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Recovery rate by action type" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Amount at risk by failure category" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Refresh" }),
    ).toBeInTheDocument();
  });

  it("refetches metrics when refresh is pressed", async () => {
    const { client, fetchImpl } = happyPathClient();
    render(<DashboardClient apiClient={client} />);

    await screen.findByText("Revenue at Risk");
    const initialCalls = fetchImpl.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(fetchImpl.mock.calls.length).toBeGreaterThan(initialCalls);
    });
    expect(await screen.findByText("Revenue at Risk")).toBeInTheDocument();
  });
});
