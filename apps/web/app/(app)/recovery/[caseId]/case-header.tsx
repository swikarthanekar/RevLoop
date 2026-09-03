"use client";

import Link from "next/link";

import { StatusBadge } from "@/components/status-badge/status-badge";
import { SegmentBadge } from "@/app/(app)/recovery/recovery-badges";
import {
  formatExactTimestamp,
  formatRelativeTime,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/recovery/recovery-format";
import type {
  CaseCore,
  CaseSource,
  CustomerDetail,
} from "@/app/(app)/recovery/[caseId]/case-types";

interface CaseHeaderProps {
  caseCore: CaseCore;
  customer: CustomerDetail;
  source: CaseSource;
  onRefresh: () => void;
  isRefreshing: boolean;
}

/**
 * Case identity strip: customer, amount at risk, case type, state and source.
 * Money is the visual anchor, matching the dashboard's money-first hierarchy.
 */
export function CaseHeader({
  caseCore,
  customer,
  source,
  onRefresh,
  isRefreshing,
}: CaseHeaderProps) {
  return (
    <header className="rounded-lg border border-neutral-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            href="/recovery"
            className="text-xs font-medium text-neutral-500 hover:text-neutral-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
          >
            ← Recovery Opportunities
          </Link>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-neutral-900">
            {customer.display_name}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <SegmentBadge segment={customer.segment} />
            <StatusBadge status={caseCore.status} />
            <span className="rounded border border-neutral-200 bg-neutral-50 px-1.5 py-0.5 text-[11px] font-medium text-neutral-700">
              {humanizeEnumLabel(caseCore.case_type)}
            </span>
            <span className="rounded border border-neutral-200 bg-neutral-50 px-1.5 py-0.5 text-[11px] font-medium text-neutral-700">
              Source: {humanizeEnumLabel(source.type)}
            </span>
          </div>
        </div>

        <div className="flex items-start gap-6">
          <div className="text-right">
            <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
              Amount at risk
            </p>
            <p className="mt-1 text-3xl font-semibold tabular-nums text-neutral-900">
              {safeMoney(caseCore.amount_at_risk_minor, caseCore.currency)}
            </p>
            <p className="mt-1 text-xs text-neutral-500">
              Lifetime value{" "}
              <span className="tabular-nums">
                {safeMoney(customer.lifetime_value_minor, caseCore.currency)}
              </span>
            </p>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-busy={isRefreshing}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRefreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-2 border-t border-neutral-100 pt-3 text-xs">
        <div>
          <dt className="inline text-neutral-500">Opened </dt>
          <dd className="inline text-neutral-800">
            <time
              dateTime={caseCore.opened_at}
              title={formatExactTimestamp(caseCore.opened_at)}
            >
              {formatRelativeTime(caseCore.opened_at)}
            </time>
          </dd>
        </div>
        <div>
          <dt className="inline text-neutral-500">Last transition </dt>
          <dd className="inline text-neutral-800">
            <time
              dateTime={caseCore.last_transition_at}
              title={formatExactTimestamp(caseCore.last_transition_at)}
            >
              {formatRelativeTime(caseCore.last_transition_at)}
            </time>
          </dd>
        </div>
        <div>
          <dt className="inline text-neutral-500">Case version </dt>
          <dd className="inline tabular-nums text-neutral-800">
            {caseCore.version}
          </dd>
        </div>
      </dl>
    </header>
  );
}
