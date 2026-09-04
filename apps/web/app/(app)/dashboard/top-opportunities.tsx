import Link from "next/link";

import { StatusBadge } from "@/components/status-badge/status-badge";
import {
  DashboardSection,
  SectionEmptyNote,
} from "@/app/(app)/dashboard/dashboard-section";
import {
  formatRate,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/dashboard/dashboard-format";
import type { RecoveryCaseListItem } from "@/app/(app)/dashboard/dashboard-types";

interface TopOpportunitiesProps {
  items: RecoveryCaseListItem[];
  /** True when the case-list request failed while the summary succeeded. */
  unavailable: boolean;
}

const HEADER_CELL =
  "px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-muted";

/**
 * Highest-priority recoverable cases. Only fields supplied by the recovery-case
 * list contract are shown, and nullable fields render as an explicit dash.
 */
export function TopOpportunities({ items, unavailable }: TopOpportunitiesProps) {
  return (
    <DashboardSection
      title="Top recovery opportunities"
      description="Highest-priority open cases, ranked by the backend priority score."
    >
      {unavailable ? (
        <SectionEmptyNote>
          Recovery cases could not be loaded right now. Dashboard metrics above
          are unaffected.
        </SectionEmptyNote>
      ) : items.length === 0 ? (
        <SectionEmptyNote>
          There are no open recovery opportunities to review.
        </SectionEmptyNote>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[46rem] border-collapse text-sm">
            <caption className="sr-only">
              Top recovery opportunities ranked by priority score
            </caption>
            <thead>
              <tr className="border-b border-line text-left">
                <th scope="col" className={HEADER_CELL}>
                  Customer
                </th>
                <th scope="col" className={`${HEADER_CELL} text-right`}>
                  At risk
                </th>
                <th scope="col" className={`${HEADER_CELL} text-right`}>
                  Expected recoverable
                </th>
                <th scope="col" className={`${HEADER_CELL} text-right`}>
                  Recovery probability
                </th>
                <th scope="col" className={HEADER_CELL}>
                  Status
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
                  className="border-b border-line last:border-b-0 hover:bg-surface-hover"
                >
                  <th scope="row" className="px-4 py-3 text-left font-normal">
                    <span className="block font-medium text-ink">
                      {item.customer.display_name}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink-muted">
                      {humanizeEnumLabel(item.customer.segment)}
                      {item.failure_category
                        ? ` · ${humanizeEnumLabel(item.failure_category)}`
                        : ""}
                    </span>
                  </th>
                  <td className="px-4 py-3 text-right font-medium tabular-nums text-ink">
                    {safeMoney(item.amount_at_risk_minor, item.currency)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-ink">
                    {item.expected_recoverable_minor === null
                      ? "—"
                      : safeMoney(item.expected_recoverable_minor, item.currency)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-ink">
                    {item.recovery_probability === null
                      ? "—"
                      : formatRate(item.recovery_probability)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/recovery/${item.id}`}
                      className="inline-flex items-center rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
                    >
                      View case
                      <span className="sr-only">
                        {` for ${item.customer.display_name}`}
                      </span>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </DashboardSection>
  );
}
