import { InlineSkeleton } from "@/components/async-state/loading-state";

/**
 * Header + section skeletons mirroring the loaded layout, so the page does not
 * shift when authoritative data arrives. No placeholder values are shown.
 */
export function CaseDetailSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true">
      <span className="sr-only">Loading recovery case</span>

      <div className="rounded-lg border border-neutral-200 bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <InlineSkeleton className="h-3 w-32" />
            <InlineSkeleton className="mt-2 h-7 w-56" />
            <div className="mt-2 flex gap-2">
              <InlineSkeleton className="h-5 w-20" />
              <InlineSkeleton className="h-5 w-24" />
            </div>
          </div>
          <div className="text-right">
            <InlineSkeleton className="h-3 w-24" />
            <InlineSkeleton className="mt-2 h-8 w-32" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {["failure", "decision", "action"].map((section) => (
          <div
            key={section}
            className="space-y-3 rounded-lg border border-neutral-200 bg-white p-4"
          >
            <InlineSkeleton className="h-4 w-32" />
            <InlineSkeleton className="h-4 w-full" />
            <InlineSkeleton className="h-4 w-5/6" />
            <InlineSkeleton className="h-4 w-4/6" />
          </div>
        ))}
      </div>

      <div className="space-y-3 rounded-lg border border-neutral-200 bg-white p-4">
        <InlineSkeleton className="h-4 w-48" />
        {[0, 1, 2].map((row) => (
          <InlineSkeleton key={row} className="h-4 w-full" />
        ))}
      </div>
    </div>
  );
}
