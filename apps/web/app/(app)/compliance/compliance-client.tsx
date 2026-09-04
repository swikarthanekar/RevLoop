"use client";

import { ErrorState } from "@/components/async-state/error-state";
import { PageSectionSkeleton } from "@/components/async-state/loading-state";
import type { ApiClient } from "@/lib/api/api-client";
import { ComplianceGuardrails } from "@/app/(app)/compliance/compliance-guardrails";
import { useComplianceData } from "@/app/(app)/compliance/use-compliance-data";

interface ComplianceClientProps {
  /** Optional client injection seam used by tests. */
  apiClient?: ApiClient;
}

/**
 * Stateful compliance container. Owns loading and error presentation and
 * keeps every failure localised to this page.
 */
export function ComplianceClient({ apiClient }: ComplianceClientProps) {
  const { state, isRefreshing, refresh } = useComplianceData(apiClient);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-neutral-900">
            Compliance Guardrails
          </h1>
          <p className="mt-1 text-sm text-neutral-600">
            The exact merchant policy the decision engine enforces on every
            recovery action -- not a description of intended behavior.
          </p>
        </div>

        <button
          type="button"
          onClick={refresh}
          disabled={isRefreshing}
          aria-busy={isRefreshing}
          className="inline-flex items-center rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-medium text-neutral-800 hover:bg-neutral-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isRefreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {state.status === "loading" ? (
        <div className="space-y-4" aria-busy="true">
          <span className="sr-only">Loading compliance guardrails</span>
          <PageSectionSkeleton title="Loading policy limits" />
          <PageSectionSkeleton title="Loading action-type groupings" />
        </div>
      ) : null}

      {state.status === "error" ? (
        <ErrorState error={state.error} onRetry={refresh} />
      ) : null}

      {state.status === "ready" ? (
        <ComplianceGuardrails policy={state.policy} />
      ) : null}
    </div>
  );
}
