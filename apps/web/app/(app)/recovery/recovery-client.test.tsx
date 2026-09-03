import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

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

import { RecoveryClient } from "@/app/(app)/recovery/recovery-client";
import { ApiClient } from "@/lib/api/api-client";
import { NullAccessTokenProvider } from "@/lib/auth/token-provider";
import { formatMoney } from "@/lib/money/format-money";
import {
  emptyRecoveryListFixture,
  pagedRecoveryListFixture,
  recoveryListFixture,
  scoredCaseFixture,
} from "@/app/(app)/recovery/__fixtures__/recovery-fixtures";

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
 * Builds a client on the real transport so tests exercise the shared ApiClient
 * and its error-envelope parsing rather than a hand-rolled stub.
 */
function buildClient(
  routeFor: (url: string, callIndex: number) => RouteBody,
) {
  let callIndex = 0;
  const fetchImpl = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
    const route = routeFor(String(input), callIndex);
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

function okClient(body: unknown = recoveryListFixture) {
  return buildClient(() => ({ status: 200, body }));
}

/** Client whose error message contains internals that must never reach the UI. */
function leakyErrorClient() {
  return buildClient(() => ({
    status: 500,
    body: {
      error: {
        code: "INTERNAL_ERROR",
        message: "Traceback (most recent call last): psycopg2.OperationalError",
        request_id: "req_recovery_2",
      },
    },
  }));
}

/** Query string of the most recent request the client made. */
function lastQuery(fetchImpl: { mock: { calls: unknown[][] } }): URLSearchParams {
  const url = String(fetchImpl.mock.calls[fetchImpl.mock.calls.length - 1][0]);
  return new URLSearchParams(url.slice(url.indexOf("?") + 1));
}

/**
 * The loading skeleton also renders a <table>, so results queries target the
 * real table by its caption rather than matching whichever table appears first.
 */
const RESULTS_TABLE = { name: /ordered by the selected sort/ };
const findResultsTable = () => screen.findByRole("table", RESULTS_TABLE);
const queryResultsTable = () => screen.queryByRole("table", RESULTS_TABLE);

beforeEach(() => {
  pushMock.mockClear();
});

describe("RecoveryClient", () => {
  it("renders the documented columns", async () => {
    const { client } = okClient();
    render(<RecoveryClient apiClient={client} />);

    const table = await findResultsTable();
    for (const column of [
      "Customer",
      "Amount at risk",
      "Failure",
      "P(Recovery)",
      "Expected recoverable",
      "Recommendation",
      "Confidence",
      "Status",
      "Opened",
    ]) {
      expect(
        within(table).getByRole("columnheader", { name: column }),
      ).toBeInTheDocument();
    }
  });

  it("requests backend priority descending by default", async () => {
    const { client, fetchImpl } = okClient();
    render(<RecoveryClient apiClient={client} />);

    await findResultsTable();
    expect(lastQuery(fetchImpl).get("sort")).toBe("priority_desc");
    expect(lastQuery(fetchImpl).get("offset")).toBe("0");
  });

  it("renders money and probability from the contract", async () => {
    const { client } = okClient();
    render(<RecoveryClient apiClient={client} />);

    const row = await screen.findByRole("row", { name: /Acme Learning/ });

    expect(within(row).getByText(formatMoney(499900, "INR"))).toBeInTheDocument();
    expect(within(row).getByText(formatMoney(409918, "INR"))).toBeInTheDocument();
    expect(within(row).getByText("82.0%")).toBeInTheDocument();
    expect(within(row).getByText("87%")).toBeInTheDocument();
    expect(within(row).getByText("Recommended")).toBeInTheDocument();
    expect(within(row).getByText("Payment rail downtime")).toBeInTheDocument();
    expect(within(row).getByText("High value")).toBeInTheDocument();
  });

  it("shows a dash instead of inventing values for null fields", async () => {
    const { client } = okClient();
    render(<RecoveryClient apiClient={client} />);

    const row = await screen.findByRole("row", { name: /Northwind/ });
    // failure category, P(Recovery), expected recoverable, recommendation, confidence
    expect(within(row).getAllByText("—")).toHaveLength(5);
  });

  it("renders open time as a time element with an exact tooltip", async () => {
    const { client } = okClient();
    render(<RecoveryClient apiClient={client} />);

    const row = await screen.findByRole("row", { name: /Acme Learning/ });
    // The relative wording drifts with the clock, so assert the stable parts;
    // relative formatting itself is unit-tested with an injected `now`.
    const opened = row.querySelector("time");
    expect(opened).not.toBeNull();
    expect(opened).toHaveAttribute("datetime", scoredCaseFixture.opened_at);
    expect(opened).toHaveAttribute("title", "30 Aug 2026, 08:20 UTC");
    expect(opened?.textContent).toMatch(/ago|just now/);
  });

  it("navigates to the case detail route when a row is clicked", async () => {
    const { client } = okClient();
    render(<RecoveryClient apiClient={client} />);

    const row = await screen.findByRole("row", { name: /Acme Learning/ });
    fireEvent.click(row);

    expect(pushMock).toHaveBeenCalledWith(
      "/recovery/11111111-1111-4111-8111-111111111111",
    );
  });

  it("exposes a keyboard-reachable View link to the same route", async () => {
    const { client } = okClient();
    render(<RecoveryClient apiClient={client} />);

    const row = await screen.findByRole("row", { name: /Acme Learning/ });
    const link = within(row).getByRole("link", { name: /View/ });

    expect(link).toHaveAttribute(
      "href",
      "/recovery/11111111-1111-4111-8111-111111111111",
    );
    // The accessible label names the customer, so the control is not a bare "View".
    expect(link.textContent).toContain("Acme Learning");
  });

  it("maps status chips onto repeated status parameters", async () => {
    const { client, fetchImpl } = okClient();
    render(<RecoveryClient apiClient={client} />);
    await findResultsTable();

    fireEvent.click(screen.getByRole("button", { name: "Recommended" }));

    await waitFor(() => {
      expect(lastQuery(fetchImpl).getAll("status")).toEqual(["RECOMMENDED"]);
    });

    fireEvent.click(screen.getByRole("button", { name: "Failed" }));

    await waitFor(() => {
      expect(lastQuery(fetchImpl).getAll("status")).toEqual([
        "RECOMMENDED",
        "FAILED",
      ]);
    });
  });

  it("maps the minimum amount filter to minor units", async () => {
    const { client, fetchImpl } = okClient();
    render(<RecoveryClient apiClient={client} />);
    await findResultsTable();

    fireEvent.change(screen.getByLabelText("Minimum amount at risk (₹)"), {
      target: { value: "4999" },
    });

    await waitFor(() => {
      expect(lastQuery(fetchImpl).get("min_amount_minor")).toBe("499900");
    });
  });

  it("maps the debounced search box onto the search parameter", async () => {
    const { client, fetchImpl } = okClient();
    render(<RecoveryClient apiClient={client} />);
    await findResultsTable();

    fireEvent.change(screen.getByLabelText("Search customer"), {
      target: { value: "Acme" },
    });

    await waitFor(() => {
      expect(lastQuery(fetchImpl).get("search")).toBe("Acme");
    });
  });

  it("maps the sort control onto the sort parameter", async () => {
    const { client, fetchImpl } = okClient();
    render(<RecoveryClient apiClient={client} />);
    await findResultsTable();

    fireEvent.change(screen.getByLabelText("Sort by"), {
      target: { value: "amount_desc" },
    });

    await waitFor(() => {
      expect(lastQuery(fetchImpl).get("sort")).toBe("amount_desc");
    });
  });

  it("offers only failure categories the backend actually returned", async () => {
    const { client } = okClient();
    render(<RecoveryClient apiClient={client} />);
    await findResultsTable();

    const select = screen.getByLabelText("Failure category");
    await waitFor(() => {
      expect(
        within(select).getByRole("option", { name: "Payment rail downtime" }),
      ).toBeInTheDocument();
    });
    expect(within(select).getAllByRole("option")).toHaveLength(2);
  });

  it("renders the global empty state when nothing is filtered", async () => {
    const { client } = okClient(emptyRecoveryListFixture);
    render(<RecoveryClient apiClient={client} />);

    expect(
      await screen.findByText("No active recovery opportunities"),
    ).toBeInTheDocument();
    expect(queryResultsTable()).not.toBeInTheDocument();
  });

  it("renders the filtered empty state when filters are active", async () => {
    const { client } = buildClient((url) =>
      url.includes("status=")
        ? { status: 200, body: emptyRecoveryListFixture }
        : { status: 200, body: recoveryListFixture },
    );
    render(<RecoveryClient apiClient={client} />);
    await findResultsTable();

    fireEvent.click(screen.getByRole("button", { name: "Stopped" }));

    expect(
      await screen.findByText("No recovery cases match these filters"),
    ).toBeInTheDocument();
  });

  it("shows an inline error with retry and preserves the active filters", async () => {
    let failNext = true;
    const { client } = buildClient(() => {
      if (failNext) {
        failNext = false;
        return {
          status: 500,
          body: {
            error: {
              code: "INTERNAL_ERROR",
              message: "Case listing failed.",
              request_id: "req_recovery_1",
            },
          },
        };
      }
      return { status: 200, body: recoveryListFixture };
    });

    render(<RecoveryClient apiClient={client} />);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Reference: req_recovery_1")).toBeInTheDocument();
    // Filter bar and heading stay mounted so the failure is localized.
    expect(screen.getByLabelText("Search customer")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Recovery Opportunities", level: 1 }),
    ).toBeInTheDocument();

    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));

    expect(await findResultsTable()).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("keeps user filters after an error", async () => {
    const { client } = buildClient((url) =>
      url.includes("search=Acme")
        ? {
            status: 500,
            body: { error: { code: "INTERNAL_ERROR", message: "boom" } },
          }
        : { status: 200, body: recoveryListFixture },
    );

    render(<RecoveryClient apiClient={client} />);
    await findResultsTable();

    fireEvent.change(screen.getByLabelText("Search customer"), {
      target: { value: "Acme" },
    });

    await screen.findByRole("alert");
    expect(screen.getByLabelText("Search customer")).toHaveValue("Acme");
  });

  it("never exposes raw backend internals in the error message", async () => {
    const { client } = leakyErrorClient();
    render(<RecoveryClient apiClient={client} />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).not.toContain("Traceback");
    expect(alert.textContent).not.toContain("psycopg2");
  });

  it("shows a skeleton that preserves the column headers while loading", async () => {
    const pending: { resolve: ((value: Response) => void) | null } = {
      resolve: null,
    };
    const fetchImpl = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          pending.resolve = resolve;
        }),
    );

    const client = new ApiClient({
      baseUrl: "http://api.test",
      tokenProvider: new NullAccessTokenProvider(),
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    const { container } = render(<RecoveryClient apiClient={client} />);

    expect(screen.getByText("Loading recovery cases")).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(
      screen.getByRole("columnheader", { name: "Amount at risk" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Acme Learning")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(fetchImpl).toHaveBeenCalledTimes(1);
      expect(pending.resolve).not.toBeNull();
    });

    // Resolve the in-flight request and wait for the settled UI so the hook's
    // state update happens inside RTL's async act boundary.
    pending.resolve!(jsonResponse({ status: 200, body: recoveryListFixture }));
    await findResultsTable();
  });

  it("paginates using backend-reported totals", async () => {
    const { client, fetchImpl } = okClient(pagedRecoveryListFixture);
    render(<RecoveryClient apiClient={client} />);

    await findResultsTable();
    expect(
      await screen.findByText("Showing 1–25 of 47 cases"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(lastQuery(fetchImpl).get("offset")).toBe("25");
    });
  });

  it("reports the backend total in the header without aggregating amounts", async () => {
    const { client } = okClient(pagedRecoveryListFixture);
    render(<RecoveryClient apiClient={client} />);

    expect(
      await screen.findByText(/47 cases, ordered by the selected sort/),
    ).toBeInTheDocument();
  });

  it("resets pagination when a filter changes", async () => {
    const { client, fetchImpl } = okClient(pagedRecoveryListFixture);
    render(<RecoveryClient apiClient={client} />);
    await findResultsTable();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(lastQuery(fetchImpl).get("offset")).toBe("25");
    });

    fireEvent.click(screen.getByRole("button", { name: "Recommended" }));
    await waitFor(() => {
      expect(lastQuery(fetchImpl).get("offset")).toBe("0");
    });
  });

  it("clears all filters back to the documented defaults", async () => {
    const { client, fetchImpl } = okClient();
    render(<RecoveryClient apiClient={client} />);
    await findResultsTable();

    fireEvent.click(screen.getByRole("button", { name: "Recommended" }));
    await waitFor(() => {
      expect(lastQuery(fetchImpl).has("status")).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    await waitFor(() => {
      const params = lastQuery(fetchImpl);
      expect(params.has("status")).toBe(false);
      expect(params.get("sort")).toBe("priority_desc");
    });
  });
});
