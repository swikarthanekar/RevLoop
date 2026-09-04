"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { StatusBadge } from "@/components/status-badge/status-badge";
import {
  ConfidenceMeter,
  SegmentBadge,
} from "@/app/(app)/recovery/recovery-badges";
import {
  formatExactTimestamp,
  formatRate,
  formatRelativeTime,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/recovery/recovery-format";
import type { RecoveryCaseListItem } from "@/app/(app)/recovery/recovery-types";

interface RecoveryTableProps {
  items: RecoveryCaseListItem[];
}

const HEADER_CELL =
  "whitespace-nowrap px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-muted";

export function caseDetailHref(caseId: string): string {
  return `/recovery/${caseId}`;
}

/**
 * Prioritized recovery cases. Every column renders a value supplied by the list
 * contract; nullable fields render an explicit dash rather than a placeholder
 * number. Ordering is whatever the backend returned — the table never re-ranks.
 */
export function RecoveryTable({ items }: RecoveryTableProps) {
  const router = useRouter();

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[72rem] border-collapse text-sm">
        <caption className="sr-only">
          Recovery opportunities, ordered by the selected sort
        </caption>
        <thead>
          <tr className="border-b border-line text-left">
            <th scope="col" className={HEADER_CELL}>
              Customer
            </th>
            <th scope="col" className={`${HEADER_CELL} text-right`}>
              Amount at risk
            </th>
            <th scope="col" className={HEADER_CELL}>
              Failure
            </th>
            <th scope="col" className={`${HEADER_CELL} text-right`}>
              P(Recovery)
            </th>
            <th scope="col" className={`${HEADER_CELL} text-right`}>
              Expected recoverable
            </th>
            <th scope="col" className={HEADER_CELL}>
              Recommendation
            </th>
            <th scope="col" className={HEADER_CELL}>
              Confidence
            </th>
            <th scope="col" className={HEADER_CELL}>
              Status
            </th>
            <th scope="col" className={HEADER_CELL}>
              Opened
            </th>
            <th scope="col" className={`${HEADER_CELL} text-right`}>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={item.id}
              onClick={() => router.push(caseDetailHref(item.id))}
              className="cursor-pointer border-b border-line last:border-b-0 hover:bg-surface-hover"
            >
              <th scope="row" className="px-3 py-3 text-left font-normal">
                <span className="block font-medium text-ink">
                  {item.customer.display_name}
                </span>
                <span className="mt-1 block">
                  <SegmentBadge segment={item.customer.segment} />
                </span>
              </th>
              <td className="whitespace-nowrap px-3 py-3 text-right font-semibold tabular-nums text-ink">
                {safeMoney(item.amount_at_risk_minor, item.currency)}
              </td>
              <td className="px-3 py-3 text-ink">
                {humanizeEnumLabel(item.failure_category)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums text-ink">
                {formatRate(item.recovery_probability)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums text-ink">
                {safeMoney(item.expected_recoverable_minor, item.currency)}
              </td>
              <td className="px-3 py-3 text-ink">
                {humanizeEnumLabel(item.recommended_action)}
              </td>
              <td className="whitespace-nowrap px-3 py-3">
                <ConfidenceMeter confidence={item.confidence} />
              </td>
              <td className="whitespace-nowrap px-3 py-3">
                <StatusBadge status={item.status} />
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-ink">
                <time
                  dateTime={item.opened_at}
                  title={formatExactTimestamp(item.opened_at)}
                >
                  {formatRelativeTime(item.opened_at)}
                </time>
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right">
                <Link
                  href={caseDetailHref(item.id)}
                  onClick={(event) => event.stopPropagation()}
                  className="inline-flex items-center rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
                >
                  View
                  <span className="sr-only">
                    {` case for ${item.customer.display_name}`}
                  </span>
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
