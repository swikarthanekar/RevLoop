"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState } from "@/components/async-state/error-state";
import type { ApiClient } from "@/lib/api/api-client";
import { OpportunityPortfolio } from "@/app/(app)/recovery/opportunity-portfolio";
import { RecoveryFilters } from "@/app/(app)/recovery/recovery-filters";
import { RecoveryPagination } from "@/app/(app)/recovery/recovery-pagination";
import { RecoveryTable } from "@/app/(app)/recovery/recovery-table";
import { RecoveryTableSkeleton } from "@/app/(app)/recovery/recovery-skeleton";
import { buildRecoveryCasesQuery } from "@/app/(app)/recovery/recovery-query";
import { formatCount } from "@/app/(app)/recovery/recovery-format";
import {
  DEFAULT_PAGE_SIZE,
  EMPTY_FILTERS,
  hasActiveFilters,
  mergeObservedOptions,
  type RecoveryFilters as RecoveryFiltersState,
} from "@/app/(app)/recovery/recovery-types";
import { useRecoveryCases } from "@/app/(app)/recovery/use-recovery-cases";

/** Keeps typing from firing a request per keystroke. */
export const SEARCH_DEBOUNCE_MS = 300;

interface RecoveryClientProps {
  /** Optional client injection seam used by tests. */
  apiClient?: ApiClient;
}

/**
 * Recovery Opportunities list. Owns filter, sort and pagination state and keeps
 * every failure localised to this page. Ordering and totals come from the
 * backend; nothing is re-ranked or aggregated in the browser.
 */
export function RecoveryClient({ apiClient }: RecoveryClientProps) {
  const [filters, setFilters] = useState<RecoveryFiltersState>(EMPTY_FILTERS);
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [caseTypeOptions, setCaseTypeOptions] = useState<string[]>([]);
  const [failureCategoryOptions, setFailureCategoryOptions] = useState<string[]>(
    [],
  );

  useEffect(() => {
    const timer = setTimeout(
      () => setDebouncedSearch(filters.search),
      SEARCH_DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [filters.search]);

  const query = useMemo(
    () =>
      buildRecoveryCasesQuery(
        { ...filters, search: debouncedSearch },
        { limit: DEFAULT_PAGE_SIZE, offset },
      ),
    [filters, debouncedSearch, offset],
  );

  const { state, refresh } = useRecoveryCases(query, apiClient);

  // Filter dropdowns offer only values the backend has actually returned,
  // because the contract types these fields as free-form strings.
  useEffect(() => {
    if (state.status !== "ready") {
      return;
    }
    const items = state.data.items;
    setCaseTypeOptions((previous) =>
      mergeObservedOptions(
        previous,
        items.map((item) => item.case_type),
      ),
    );
    setFailureCategoryOptions((previous) =>
      mergeObservedOptions(
        previous,
        items.map((item) => item.failure_category),
      ),
    );
  }, [state]);

  const handleFilterChange = useCallback((next: RecoveryFiltersState) => {
    setFilters(next);
    setOffset(0);
  }, []);

  const handleClear = useCallback(() => {
    setFilters(EMPTY_FILTERS);
    setOffset(0);
  }, []);

  const filtersActive = hasActiveFilters(filters);
  const total = state.status === "ready" ? state.data.total : null;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
          Recovery Opportunities
        </h1>
        <p className="mt-1 text-sm text-neutral-600">
          {total === null
            ? "Prioritized recoverable revenue cases."
            : `${formatCount(total)} ${total === 1 ? "case" : "cases"}${
                filtersActive ? " match these filters" : ""
              }, ordered by the selected sort.`}
        </p>
      </div>

      <RecoveryFilters
        filters={filters}
        onChange={handleFilterChange}
        onClear={handleClear}
        caseTypeOptions={caseTypeOptions}
        failureCategoryOptions={failureCategoryOptions}
      />

      {state.status === "loading" ? (
        <div className="rounded-lg border border-neutral-200 bg-white p-2">
          <RecoveryTableSkeleton />
        </div>
      ) : null}

      {state.status === "error" ? (
        <ErrorState error={state.error} onRetry={refresh} />
      ) : null}

      {state.status === "ready" && state.data.items.length === 0 ? (
        <EmptyState
          title={
            filtersActive
              ? "No recovery cases match these filters"
              : "No active recovery opportunities"
          }
          description={
            filtersActive
              ? "Adjust or clear the filters above to widen the search."
              : "New cases appear here as payment failures are detected."
          }
        />
      ) : null}

      {state.status === "ready" && state.data.items.length > 0 ? (
        <div className="space-y-4">
          <OpportunityPortfolio
            items={state.data.items}
            currency={state.data.items[0]?.currency ?? "INR"}
          />
          <div className="space-y-3 rounded-lg border border-neutral-200 bg-white p-2">
            <RecoveryTable items={state.data.items} />
            <RecoveryPagination
              total={state.data.total}
              limit={state.data.limit}
              offset={state.data.offset}
              onOffsetChange={setOffset}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
