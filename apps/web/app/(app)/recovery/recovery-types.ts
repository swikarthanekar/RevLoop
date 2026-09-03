import type { components } from "@/types/generated/api";

/**
 * Backend-authoritative contracts, aliased from the generated OpenAPI schema so
 * the recovery list never redefines a domain shape by hand.
 */
export type RecoveryCaseListItem = components["schemas"]["RecoveryCaseListItem"];
export type RecoveryCaseListResponse =
  components["schemas"]["RecoveryCaseListResponse"];
export type RecoveryCaseSort = components["schemas"]["RecoveryCaseSort"];
export type RecoveryCaseStatus = components["schemas"]["RecoveryCaseStatus"];

/** Documented sort options, in the order they are offered in the UI. */
export const SORT_OPTIONS: ReadonlyArray<{
  value: RecoveryCaseSort;
  label: string;
}> = [
  { value: "priority_desc", label: "Priority (highest first)" },
  { value: "amount_desc", label: "Amount at risk (highest first)" },
  { value: "opened_desc", label: "Most recently opened" },
];

/** Spec default: priority descending. */
export const DEFAULT_SORT: RecoveryCaseSort = "priority_desc";

/** Contract allows 1..100; 25 matches the documented example page size. */
export const DEFAULT_PAGE_SIZE = 25;

/**
 * All case statuses the backend can report. Sourced from the generated
 * `RecoveryCaseStatus` enum rather than a handwritten list.
 */
export const ALL_STATUSES: readonly RecoveryCaseStatus[] = [
  "DETECTED",
  "ANALYZING",
  "RECOMMENDED",
  "AWAITING_APPROVAL",
  "SCHEDULED",
  "EXECUTING",
  "WAITING_FOR_OUTCOME",
  "RECOVERED",
  "FAILED",
  "STOPPED",
];

/** User-controlled filter state. Mirrors only documented query parameters. */
export interface RecoveryFilters {
  statuses: RecoveryCaseStatus[];
  caseType: string | null;
  failureCategory: string | null;
  /** Raw user input in whole major units (rupees). */
  minAmountMajor: string;
  search: string;
  sort: RecoveryCaseSort;
}

export const EMPTY_FILTERS: RecoveryFilters = {
  statuses: [],
  caseType: null,
  failureCategory: null,
  minAmountMajor: "",
  search: "",
  sort: DEFAULT_SORT,
};

/**
 * Accumulates the distinct values observed in API responses for a free-form
 * field, so filter dropdowns only ever offer values the backend actually
 * returned. Returns the previous array unchanged when nothing new appeared, so
 * callers can store the result in state without re-render loops.
 */
export function mergeObservedOptions(
  previous: string[],
  incoming: ReadonlyArray<string | null | undefined>,
): string[] {
  const merged = new Set(previous);
  let changed = false;

  for (const value of incoming) {
    if (!value) {
      continue;
    }
    const trimmed = value.trim();
    if (!trimmed || merged.has(trimmed)) {
      continue;
    }
    merged.add(trimmed);
    changed = true;
  }

  return changed ? [...merged].sort() : previous;
}

/** True when the user has narrowed the list in any way. */
export function hasActiveFilters(filters: RecoveryFilters): boolean {
  return (
    filters.statuses.length > 0 ||
    filters.caseType !== null ||
    filters.failureCategory !== null ||
    filters.minAmountMajor.trim() !== "" ||
    filters.search.trim() !== ""
  );
}
