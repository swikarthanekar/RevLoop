"use client";

import Link from "next/link";

import { EmptyState, ErrorState } from "@/components/async-state/error-state";
import type { ApiClient } from "@/lib/api/api-client";
import { DashboardHeader } from "@/app/(app)/dashboard/dashboard-header";
import { DashboardSkeleton } from "@/app/(app)/dashboard/dashboard-skeleton";
import { DashboardView } from "@/app/(app)/dashboard/dashboard-view";
import { formatSourceLabel } from "@/app/(app)/dashboard/dashboard-format";
import { isDashboardEmpty } from "@/app/(app)/dashboard/dashboard-types";
import { useDashboardData } from "@/app/(app)/dashboard/use-dashboard-data";

interface DashboardClientProps {
  /** Optional client injection seam used by tests. */
  apiClient?: ApiClient;
}

/**
 * Stateful dashboard container. Owns loading, error and empty presentation and
 * keeps every failure localised to this page.
 */
export function DashboardClient({ apiClient }: DashboardClientProps) {
  const { state, isRefreshing, refresh } = useDashboardData(apiClient);

  const sourceLabel =
    state.status === "ready"
      ? formatSourceLabel(state.data.summary.source_label)
      : null;

  return (
    <div className="space-y-6">
      <DashboardHeader
        sourceLabel={sourceLabel}
        onRefresh={refresh}
        isRefreshing={isRefreshing}
      />

      {state.status === "loading" ? <DashboardSkeleton /> : null}

      {state.status === "error" ? (
        <div className="space-y-3">
          <p className="text-sm text-neutral-700">
            Dashboard metrics are temporarily unavailable.{" "}
            <Link
              href="/recovery"
              className="font-medium text-neutral-900 underline underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
            >
              Recovery cases can still be viewed.
            </Link>
          </p>
          <ErrorState error={state.error} onRetry={refresh} />
        </div>
      ) : null}

      {state.status === "ready" && isDashboardEmpty(state.data.summary) ? (
        <EmptyState
          title="No recovery activity yet"
          description="Seed demo data or wait for a payment failure event. Metrics will appear here once the first recovery case is opened."
        />
      ) : null}

      {state.status === "ready" && !isDashboardEmpty(state.data.summary) ? (
        <DashboardView data={state.data} />
      ) : null}
    </div>
  );
}
