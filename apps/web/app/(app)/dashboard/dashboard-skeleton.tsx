import { InlineSkeleton } from "@/components/async-state/loading-state";

function KpiCardSkeleton() {
  return (
    <div className="rounded-lg border border-line bg-surface p-5">
      <InlineSkeleton className="h-3 w-28" />
      <InlineSkeleton className="mt-3 h-8 w-36" />
      <InlineSkeleton className="mt-2 h-3 w-24" />
    </div>
  );
}

function SectionSkeleton({ bodyHeight }: { bodyHeight: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-5">
      <InlineSkeleton className="h-4 w-44" />
      <InlineSkeleton className="mt-2 h-3 w-64" />
      <InlineSkeleton className={`mt-5 w-full ${bodyHeight}`} />
    </div>
  );
}

/**
 * Loading state that mirrors the final dashboard layout so the page does not
 * shift when data arrives. No placeholder numbers are rendered.
 */
export function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <span className="sr-only">Loading dashboard metrics</span>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCardSkeleton />
        <KpiCardSkeleton />
        <KpiCardSkeleton />
        <KpiCardSkeleton />
      </div>

      <SectionSkeleton bodyHeight="h-56" />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SectionSkeleton bodyHeight="h-40" />
        <SectionSkeleton bodyHeight="h-40" />
      </div>

      <SectionSkeleton bodyHeight="h-48" />
    </div>
  );
}
