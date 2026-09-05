"use client";

import { useEffect, useMemo, useState } from "react";

import { ErrorState } from "@/components/async-state/error-state";
import { ApiClient, createDefaultApiClient } from "@/lib/api/api-client";
import { ApiError, genericApiError } from "@/lib/api/api-error";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import {
  formatExactTimestamp,
  humanizeEnumLabel,
} from "@/app/(app)/recovery/recovery-format";
import type {
  ProviderEventsResponse,
  ProviderEventSummary,
} from "@/app/(app)/provider-events/provider-events-types";

export const PROVIDER_EVENTS_PATH = "/api/v1/provider-events?limit=25";

type State =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: ProviderEventsResponse };

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number;
  tone?: "neutral" | "success" | "danger";
}) {
  const toneClass =
    tone === "success"
      ? "text-success-ink"
      : tone === "danger"
        ? "text-danger-ink"
        : "text-ink";
  return (
    <div className="min-w-0 flex-1 px-4 py-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </dt>
      <dd className={`mt-0.5 text-xl font-semibold tabular-nums ${toneClass}`}>
        {value}
      </dd>
    </div>
  );
}

function EventRow({ event }: { event: ProviderEventSummary }) {
  return (
    <li className="border-b border-line px-4 py-3 last:border-b-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="min-w-0">
          <span className="text-sm font-medium text-ink">
            {event.event_type}
          </span>
          <span className="ml-2 font-mono text-[11px] text-ink-muted">
            {event.provider_event_id}
          </span>
        </div>
        <time
          dateTime={event.received_at}
          className="text-xs tabular-nums text-ink-muted"
        >
          {formatExactTimestamp(event.received_at)}
        </time>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <span
          className={`rounded border px-1.5 py-0.5 text-[11px] font-medium ${
            event.signature_valid
              ? "border-success-border bg-success-surface text-success-ink"
              : "border-danger-border bg-danger-surface text-danger-ink"
          }`}
        >
          {event.signature_valid ? "Signature verified" : "Signature rejected"}
        </span>
        <span className="rounded border border-line bg-surface-hover px-1.5 py-0.5 text-[11px] font-medium text-ink">
          {humanizeEnumLabel(event.processing_status)}
        </span>
        {event.duplicate_of_earlier_event ? (
          <span className="rounded border border-info-border bg-info-surface px-1.5 py-0.5 text-[11px] font-medium text-info-ink">
            Duplicate — suppressed
          </span>
        ) : null}
      </div>

      {event.processing_error ? (
        <p className="mt-1.5 text-xs text-ink-muted">{event.processing_error}</p>
      ) : null}
    </li>
  );
}

/**
 * Received provider webhooks and what the system decided about each.
 *
 * Webhook handling is where most of this system's correctness work lives --
 * HMAC verification over the raw body before parsing, deduplication on the
 * provider's own event id, stale-event precedence. All of it ran invisibly.
 *
 * Read-only on purpose. A replay control would be a write path firing while
 * someone watches, and the recorded history already carries the story.
 */
export function ProviderEventsClient({
  apiClient,
}: { apiClient?: ApiClient } = {}) {
  const client = useMemo(
    () => apiClient ?? createDefaultApiClient(createAccessTokenProvider()),
    [apiClient],
  );
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    client
      .get<ProviderEventsResponse>(PROVIDER_EVENTS_PATH)
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: "error",
            error:
              error instanceof ApiError
                ? error
                : genericApiError("network", "Unable to reach the RevLoop API."),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Provider Events
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          Every webhook Razorpay sent, whether its signature verified, and what
          the ingestion path decided.
        </p>
      </div>

      {state.status === "error" ? (
        <ErrorState error={state.error} />
      ) : state.status === "loading" ? (
        <div
          className="h-64 animate-pulse rounded-lg border border-line bg-surface"
          aria-hidden="true"
        />
      ) : (
        <>
          <dl className="flex flex-wrap divide-y divide-line rounded-lg border border-line bg-surface sm:divide-x sm:divide-y-0">
            <Stat label="Received" value={state.data.stats.total} />
            <Stat
              label="Signature verified"
              value={state.data.stats.signature_valid}
              tone="success"
            />
            <Stat
              label="Signature rejected"
              value={state.data.stats.signature_rejected}
              tone={state.data.stats.signature_rejected > 0 ? "danger" : "neutral"}
            />
            <Stat label="Processed" value={state.data.stats.processed} />
            <Stat
              label="Duplicates suppressed"
              value={state.data.stats.duplicates_suppressed}
            />
          </dl>

          <section
            aria-label="Received provider events"
            className="rounded-lg border border-line bg-surface"
          >
            {state.data.events.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-ink-muted">
                No provider events received yet. They appear here as Razorpay
                sends them.
              </p>
            ) : (
              <ul>
                {state.data.events.map((event) => (
                  <EventRow
                    key={`${event.provider}:${event.provider_event_id}:${event.received_at}`}
                    event={event}
                  />
                ))}
              </ul>
            )}
          </section>

          <div className="rounded-lg border border-line bg-surface p-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              What happens before an event is trusted
            </h2>
            <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-ink">
              <li>
                The HMAC-SHA256 signature is computed over the{" "}
                <span className="font-medium">raw request body</span>, before
                any JSON parsing, and compared with{" "}
                <code className="font-mono text-xs">hmac.compare_digest</code>.
                A mismatch is recorded and rejected — it never reaches business
                logic.
              </li>
              <li>
                The provider&rsquo;s own event id is inserted under a unique
                database constraint. A repeat delivery loses that race and is
                suppressed, so retries cannot double-apply.
              </li>
              <li>
                A stale <code className="font-mono text-xs">failed</code> event
                cannot downgrade a payment already known to be captured.
              </li>
            </ol>
            <p className="mt-2 text-[11px] text-ink-muted">
              This view is read-only. There is no replay control by design: a
              re-fired webhook is a write, and this page exists to show what
              already happened.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
