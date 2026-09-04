"use client";

import { EmptyState, ErrorState } from "@/components/async-state/error-state";
import { CaseSection } from "@/app/(app)/recovery/[caseId]/case-section";
import { AuditTimelineEntry } from "@/app/(app)/recovery/[caseId]/audit-timeline-entry";
import { AuditTimelineSkeleton } from "@/app/(app)/recovery/[caseId]/audit-timeline-skeleton";
import type { TimelineState } from "@/app/(app)/recovery/[caseId]/use-case-timeline";

interface AuditTimelineProps {
  state: TimelineState;
  onRefresh: () => void;
  isRefreshing: boolean;
}

/**
 * Agent / audit timeline (FRONTEND_SPEC Screen 4), embedded in case detail.
 *
 * Read-only. A failure here is contained to this section so the surrounding
 * case detail and its action controls remain fully usable.
 *
 * Entries are rendered in the order the endpoint returns them: API_CONTRACTS.md
 * section 10 specifies ascending order, and the backend query already sorts by
 * `created_at ASC, id ASC`, which is stable for equal timestamps. The frontend
 * does not re-sort and never infers order from event names.
 */
export function AuditTimeline({
  state,
  onRefresh,
  isRefreshing,
}: AuditTimelineProps) {
  const refreshButton = (
    <button
      type="button"
      onClick={onRefresh}
      disabled={isRefreshing}
      aria-busy={isRefreshing}
      className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {isRefreshing ? "Refreshing…" : "Refresh timeline"}
    </button>
  );

  return (
    <CaseSection
      title="Agent & audit timeline"
      headingId="case-timeline-heading"
      description="Operational history recorded by the backend for this case."
      actions={refreshButton}
    >
      {state.status === "loading" ? <AuditTimelineSkeleton /> : null}

      {state.status === "error" ? (
        <ErrorState error={state.error} onRetry={onRefresh} />
      ) : null}

      {state.status === "ready" && state.items.length === 0 ? (
        <EmptyState
          title="No audit events recorded yet"
          description="Events appear here as the backend records analysis, policy, execution and outcome activity for this case."
        />
      ) : null}

      {state.status === "ready" && state.items.length > 0 ? (
        <ol className="mt-1">
          {state.items.map((entry) => (
            <AuditTimelineEntry key={entry.id} entry={entry} />
          ))}
        </ol>
      ) : null}
    </CaseSection>
  );
}
