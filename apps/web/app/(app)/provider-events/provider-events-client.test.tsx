import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProviderEventsClient } from "@/app/(app)/provider-events/provider-events-client";
import { ApiClient } from "@/lib/api/api-client";
import { NullAccessTokenProvider } from "@/lib/auth/token-provider";
import type { ProviderEventsResponse } from "@/app/(app)/provider-events/provider-events-types";

const RESPONSE: ProviderEventsResponse = {
  stats: {
    total: 3,
    signature_valid: 2,
    signature_rejected: 1,
    processed: 1,
    ignored: 1,
    failed: 1,
    duplicates_suppressed: 1,
  },
  events: [
    {
      provider: "razorpay",
      provider_event_id: "evt_dupe",
      event_type: "payment_link.paid",
      received_at: "2026-09-05T10:00:00Z",
      processed_at: null,
      signature_valid: true,
      processing_status: "IGNORED",
      processing_error: "Duplicate event id",
      duplicate_of_earlier_event: true,
      case_id: null,
    },
    {
      provider: "razorpay",
      provider_event_id: "evt_bad",
      event_type: "payment.failed",
      received_at: "2026-09-05T09:59:00Z",
      processed_at: null,
      signature_valid: false,
      processing_status: "FAILED",
      processing_error: "INVALID_WEBHOOK_SIGNATURE",
      duplicate_of_earlier_event: false,
      case_id: null,
    },
  ],
};

function buildClient(status: number, body: unknown) {
  const fetchImpl = vi.fn(
    async (): Promise<Response> =>
      ({
        ok: status >= 200 && status < 300,
        status,
        headers: new Headers({ "content-type": "application/json" }),
        text: async () => JSON.stringify(body),
      }) as Response,
  );
  return new ApiClient({
    baseUrl: "http://api.test",
    tokenProvider: new NullAccessTokenProvider(),
    fetchImpl: fetchImpl as unknown as typeof fetch,
  });
}

describe("ProviderEventsClient", () => {
  it("distinguishes a verified signature from a rejected one", async () => {
    render(<ProviderEventsClient apiClient={buildClient(200, RESPONSE)} />);
    // Each label appears twice on purpose: once as a summary stat across all
    // traffic, once as the badge on the individual event.
    expect((await screen.findAllByText("Signature rejected")).length).toBe(2);
    expect(screen.getAllByText("Signature verified").length).toBe(2);
    expect(screen.getByText("INVALID_WEBHOOK_SIGNATURE")).toBeInTheDocument();
  });

  it("marks a suppressed duplicate", async () => {
    // The most interesting row on the page: proof the dedup constraint fired.
    render(<ProviderEventsClient apiClient={buildClient(200, RESPONSE)} />);
    expect(await screen.findByText(/Duplicate — suppressed/)).toBeInTheDocument();
  });

  it("explains what happens before an event is trusted", async () => {
    render(<ProviderEventsClient apiClient={buildClient(200, RESPONSE)} />);
    expect(await screen.findByText(/raw request body/i)).toBeInTheDocument();
    expect(screen.getByText(/hmac.compare_digest/)).toBeInTheDocument();
  });

  it("states that it is read-only and why there is no replay", async () => {
    render(<ProviderEventsClient apiClient={buildClient(200, RESPONSE)} />);
    expect(
      await screen.findByText(/no replay control by design/i),
    ).toBeInTheDocument();
  });

  it("renders an empty state rather than a broken table", async () => {
    render(
      <ProviderEventsClient
        apiClient={buildClient(200, {
          stats: {
            total: 0,
            signature_valid: 0,
            signature_rejected: 0,
            processed: 0,
            ignored: 0,
            failed: 0,
            duplicates_suppressed: 0,
          },
          events: [],
        })}
      />,
    );
    expect(
      await screen.findByText(/No provider events received yet/i),
    ).toBeInTheDocument();
  });

  it("shows an error state when the API fails", async () => {
    render(
      <ProviderEventsClient
        apiClient={buildClient(500, { error: { code: "X", message: "boom" } })}
      />,
    );
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
