"use client";

import { humanizeEnumLabel } from "@/app/(app)/recovery/recovery-format";
import { parseMinAmountMinor } from "@/app/(app)/recovery/recovery-query";
import {
  ALL_STATUSES,
  SORT_OPTIONS,
  hasActiveFilters,
  type RecoveryCaseSort,
  type RecoveryCaseStatus,
  type RecoveryFilters as RecoveryFiltersState,
} from "@/app/(app)/recovery/recovery-types";

interface RecoveryFiltersProps {
  filters: RecoveryFiltersState;
  onChange: (next: RecoveryFiltersState) => void;
  onClear: () => void;
  /**
   * Option lists observed in API responses. The contract types these fields as
   * free-form strings, so the UI offers only values the backend has returned.
   */
  caseTypeOptions: string[];
  failureCategoryOptions: string[];
}

const FIELD_LABEL = "block text-xs font-medium text-neutral-600";
const FIELD_CONTROL =
  "mt-1 w-full rounded-md border border-neutral-300 bg-white px-2.5 py-1.5 text-sm text-neutral-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500";

export function RecoveryFilters({
  filters,
  onChange,
  onClear,
  caseTypeOptions,
  failureCategoryOptions,
}: RecoveryFiltersProps) {
  const toggleStatus = (status: RecoveryCaseStatus) => {
    const next = filters.statuses.includes(status)
      ? filters.statuses.filter((value) => value !== status)
      : [...filters.statuses, status];
    onChange({ ...filters, statuses: next });
  };

  const minAmountRaw = filters.minAmountMajor.trim();
  const minAmountInvalid =
    minAmountRaw !== "" && parseMinAmountMinor(minAmountRaw) === null;

  return (
    <section
      aria-label="Recovery case filters"
      className="rounded-lg border border-neutral-200 bg-white p-4"
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div>
          <label className={FIELD_LABEL} htmlFor="recovery-search">
            Search customer
          </label>
          <input
            id="recovery-search"
            type="search"
            value={filters.search}
            onChange={(event) =>
              onChange({ ...filters, search: event.target.value })
            }
            placeholder="Name or external ID"
            className={FIELD_CONTROL}
          />
        </div>

        <div>
          <label className={FIELD_LABEL} htmlFor="recovery-case-type">
            Case type
          </label>
          <select
            id="recovery-case-type"
            value={filters.caseType ?? ""}
            onChange={(event) =>
              onChange({ ...filters, caseType: event.target.value || null })
            }
            className={FIELD_CONTROL}
          >
            <option value="">All case types</option>
            {caseTypeOptions.map((option) => (
              <option key={option} value={option}>
                {humanizeEnumLabel(option)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={FIELD_LABEL} htmlFor="recovery-failure-category">
            Failure category
          </label>
          <select
            id="recovery-failure-category"
            value={filters.failureCategory ?? ""}
            onChange={(event) =>
              onChange({
                ...filters,
                failureCategory: event.target.value || null,
              })
            }
            className={FIELD_CONTROL}
          >
            <option value="">All failure categories</option>
            {failureCategoryOptions.map((option) => (
              <option key={option} value={option}>
                {humanizeEnumLabel(option)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={FIELD_LABEL} htmlFor="recovery-min-amount">
            Minimum amount at risk (₹)
          </label>
          <input
            id="recovery-min-amount"
            type="number"
            inputMode="numeric"
            min={0}
            step={1}
            value={filters.minAmountMajor}
            onChange={(event) =>
              onChange({ ...filters, minAmountMajor: event.target.value })
            }
            placeholder="0"
            aria-invalid={minAmountInvalid}
            aria-describedby={
              minAmountInvalid ? "recovery-min-amount-hint" : undefined
            }
            className={FIELD_CONTROL}
          />
          {minAmountInvalid ? (
            <p
              id="recovery-min-amount-hint"
              className="mt-1 text-xs text-amber-700"
            >
              Enter a whole rupee amount. This filter is ignored until then.
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <fieldset className="min-w-0">
          <legend className={FIELD_LABEL}>Status</legend>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {ALL_STATUSES.map((status) => {
              const active = filters.statuses.includes(status);
              return (
                <button
                  key={status}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggleStatus(status)}
                  className={`rounded-full border px-2.5 py-1 text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 ${
                    active
                      ? "border-neutral-800 bg-neutral-800 text-white"
                      : "border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-50"
                  }`}
                >
                  {humanizeEnumLabel(status)}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="flex items-end gap-3">
          <div>
            <label className={FIELD_LABEL} htmlFor="recovery-sort">
              Sort by
            </label>
            <select
              id="recovery-sort"
              value={filters.sort}
              onChange={(event) =>
                onChange({
                  ...filters,
                  sort: event.target.value as RecoveryCaseSort,
                })
              }
              className={`${FIELD_CONTROL} w-auto`}
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {hasActiveFilters(filters) ? (
            <button
              type="button"
              onClick={onClear}
              className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
