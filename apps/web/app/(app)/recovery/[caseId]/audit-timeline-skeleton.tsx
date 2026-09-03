import { InlineSkeleton } from "@/components/async-state/loading-state";

/**
 * Timeline-shaped loading placeholder. Shows structure only — never fabricated
 * event names, summaries or timestamps.
 */
export function AuditTimelineSkeleton() {
  return (
    <div aria-busy="true">
      <span className="sr-only">Loading audit timeline</span>
      <ul className="space-y-5">
        {[0, 1, 2].map((row) => (
          <li key={row} className="flex gap-3">
            <InlineSkeleton className="mt-1 h-3 w-3 rounded-full" />
            <div className="flex-1 space-y-1.5">
              <InlineSkeleton className="h-4 w-48" />
              <InlineSkeleton className="h-4 w-full" />
              <InlineSkeleton className="h-3 w-32" />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
