import { getCurrencyFractionDigits } from "@/lib/money/format-money";
import type { RecoveryFilters } from "@/app/(app)/recovery/recovery-types";

export const RECOVERY_CASES_PATH = "/api/v1/recovery-cases";

/**
 * P0 operates in INR. The minimum-amount filter is entered in major units and
 * converted using the central currency fraction-digit logic rather than a
 * hardcoded factor of 100.
 */
export const FILTER_CURRENCY = "INR";

/**
 * Converts the minimum-amount filter from whole major units to the minor units
 * the API expects.
 *
 * Only whole major units are accepted so the conversion stays exact integer
 * arithmetic — no floating point is used for a monetary value. Anything the
 * backend would reject (blank, negative, decimal, non-numeric, unsafe integer)
 * maps to `null` and the parameter is simply omitted.
 */
export function parseMinAmountMinor(rawInput: string): number | null {
  const trimmed = rawInput.trim();
  if (!trimmed || !/^\d+$/.test(trimmed)) {
    return null;
  }
  const major = Number(trimmed);
  if (!Number.isSafeInteger(major)) {
    return null;
  }
  const minor = major * 10 ** getCurrencyFractionDigits(FILTER_CURRENCY);
  return Number.isSafeInteger(minor) ? minor : null;
}

export interface RecoveryPageRequest {
  limit: number;
  offset: number;
}

/**
 * Maps filter state onto the documented `GET /api/v1/recovery-cases` query
 * parameters. Only parameters defined by the contract are emitted, and blank or
 * invalid values are omitted rather than sent as empty strings.
 *
 * `status` is repeated once per selected value, matching the array shape in the
 * generated OpenAPI types.
 */
export function buildRecoveryCasesQuery(
  filters: RecoveryFilters,
  page: RecoveryPageRequest,
): string {
  const params = new URLSearchParams();

  for (const status of filters.statuses) {
    params.append("status", status);
  }

  if (filters.caseType) {
    params.set("case_type", filters.caseType);
  }

  if (filters.failureCategory) {
    params.set("failure_category", filters.failureCategory);
  }

  const minAmountMinor = parseMinAmountMinor(filters.minAmountMajor);
  if (minAmountMinor !== null) {
    params.set("min_amount_minor", String(minAmountMinor));
  }

  const search = filters.search.trim();
  if (search) {
    params.set("search", search);
  }

  params.set("sort", filters.sort);
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));

  return `${RECOVERY_CASES_PATH}?${params.toString()}`;
}
