import { InlineSkeleton } from "@/components/async-state/loading-state";

const COLUMN_HEADERS = [
  "Customer",
  "Amount at risk",
  "Failure",
  "P(Recovery)",
  "Expected recoverable",
  "Recommendation",
  "Confidence",
  "Status",
  "Opened",
];

const HEADER_CELL =
  "whitespace-nowrap px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-muted";

interface RecoveryTableSkeletonProps {
  rows?: number;
}

/**
 * Loading state that keeps the real column headers in place so the table does
 * not shift when rows arrive. No placeholder values are rendered.
 */
export function RecoveryTableSkeleton({ rows = 8 }: RecoveryTableSkeletonProps) {
  return (
    <div className="overflow-x-auto" aria-busy="true">
      <span className="sr-only">Loading recovery cases</span>
      <table className="w-full min-w-[72rem] border-collapse text-sm">
        <caption className="sr-only">Loading recovery opportunities</caption>
        <thead>
          <tr className="border-b border-line text-left">
            {COLUMN_HEADERS.map((header) => (
              <th key={header} scope="col" className={HEADER_CELL}>
                {header}
              </th>
            ))}
            <th scope="col" className={HEADER_CELL}>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_value, rowIndex) => (
            <tr key={rowIndex} className="border-b border-line">
              <td className="px-3 py-3">
                <InlineSkeleton className="h-4 w-40" />
                <InlineSkeleton className="mt-1.5 h-3 w-20" />
              </td>
              {COLUMN_HEADERS.slice(1).map((header) => (
                <td key={header} className="px-3 py-3">
                  <InlineSkeleton className="h-4 w-20" />
                </td>
              ))}
              <td className="px-3 py-3">
                <InlineSkeleton className="h-6 w-14" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
