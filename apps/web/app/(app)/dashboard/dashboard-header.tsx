import { InlineSkeleton } from "@/components/async-state/loading-state";

interface DashboardHeaderProps {
  /** Backend `source_label`, already humanised. Null while metrics load. */
  sourceLabel: string | null;
  onRefresh: () => void;
  isRefreshing: boolean;
}

/**
 * Page header with the demo provenance line required by the spec. The source
 * label always comes from the backend so synthetic data is never presented as
 * production revenue.
 */
export function DashboardHeader({
  sourceLabel,
  onRefresh,
  isRefreshing,
}: DashboardHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-neutral-900">
          Revenue Recovery Overview
        </h1>
        {sourceLabel === null ? (
          <InlineSkeleton className="mt-2 h-4 w-56" />
        ) : (
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-neutral-600">
            <span className="rounded border border-neutral-300 bg-neutral-50 px-1.5 py-0.5 text-xs font-medium uppercase tracking-wide text-neutral-700">
              Data source
            </span>
            {sourceLabel}
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={onRefresh}
        disabled={isRefreshing}
        aria-busy={isRefreshing}
        className="inline-flex items-center rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-medium text-neutral-800 hover:bg-neutral-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isRefreshing ? "Refreshing…" : "Refresh"}
      </button>
    </div>
  );
}
