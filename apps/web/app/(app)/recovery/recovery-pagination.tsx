"use client";

import { formatCount } from "@/app/(app)/recovery/recovery-format";

interface RecoveryPaginationProps {
  /** Backend-reported totals from the list response. */
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (nextOffset: number) => void;
}

/**
 * Offset pagination driven entirely by the `total`, `limit` and `offset` values
 * the backend returns with each page.
 */
export function RecoveryPagination({
  total,
  limit,
  offset,
  onOffsetChange,
}: RecoveryPaginationProps) {
  const safeLimit = limit > 0 ? limit : 1;
  const firstRow = total === 0 ? 0 : offset + 1;
  const lastRow = Math.min(offset + safeLimit, total);
  const hasPrevious = offset > 0;
  const hasNext = offset + safeLimit < total;

  const buttonClass =
    "rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <nav
      aria-label="Recovery cases pagination"
      className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-1 pt-3"
    >
      <p className="text-sm text-ink-muted" aria-live="polite">
        {total === 0
          ? "No cases to display"
          : `Showing ${formatCount(firstRow)}–${formatCount(lastRow)} of ${formatCount(total)} cases`}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className={buttonClass}
          disabled={!hasPrevious}
          onClick={() => onOffsetChange(Math.max(0, offset - safeLimit))}
        >
          Previous
        </button>
        <button
          type="button"
          className={buttonClass}
          disabled={!hasNext}
          onClick={() => onOffsetChange(offset + safeLimit)}
        >
          Next
        </button>
      </div>
    </nav>
  );
}
