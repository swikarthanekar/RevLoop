import { describe, expect, it } from "vitest";

import {
  RECOVERY_CASES_PATH,
  buildRecoveryCasesQuery,
  parseMinAmountMinor,
} from "@/app/(app)/recovery/recovery-query";
import {
  DEFAULT_PAGE_SIZE,
  EMPTY_FILTERS,
  hasActiveFilters,
  mergeObservedOptions,
} from "@/app/(app)/recovery/recovery-types";

const PAGE = { limit: DEFAULT_PAGE_SIZE, offset: 0 };

function paramsOf(query: string): URLSearchParams {
  return new URLSearchParams(query.slice(query.indexOf("?") + 1));
}

describe("parseMinAmountMinor", () => {
  it("converts whole rupees to minor units exactly", () => {
    expect(parseMinAmountMinor("5000")).toBe(500000);
    expect(parseMinAmountMinor("0")).toBe(0);
    expect(parseMinAmountMinor("  1200  ")).toBe(120000);
  });

  it("omits blank input", () => {
    expect(parseMinAmountMinor("")).toBeNull();
    expect(parseMinAmountMinor("   ")).toBeNull();
  });

  it("rejects values the backend contract would refuse", () => {
    expect(parseMinAmountMinor("-100")).toBeNull();
    expect(parseMinAmountMinor("12.50")).toBeNull();
    expect(parseMinAmountMinor("abc")).toBeNull();
    expect(parseMinAmountMinor("₹4999")).toBeNull();
    expect(parseMinAmountMinor("1e5")).toBeNull();
  });

  it("rejects input that would exceed safe integer range", () => {
    expect(parseMinAmountMinor("999999999999999999999")).toBeNull();
  });
});

describe("buildRecoveryCasesQuery", () => {
  it("sends only sort, limit and offset when no filters are set", () => {
    const query = buildRecoveryCasesQuery(EMPTY_FILTERS, PAGE);

    expect(query).toBe(
      `${RECOVERY_CASES_PATH}?sort=priority_desc&limit=25&offset=0`,
    );
  });

  it("defaults to backend priority descending", () => {
    expect(paramsOf(buildRecoveryCasesQuery(EMPTY_FILTERS, PAGE)).get("sort")).toBe(
      "priority_desc",
    );
  });

  it("repeats the status parameter once per selected status", () => {
    const query = buildRecoveryCasesQuery(
      { ...EMPTY_FILTERS, statuses: ["RECOMMENDED", "AWAITING_APPROVAL"] },
      PAGE,
    );

    expect(paramsOf(query).getAll("status")).toEqual([
      "RECOMMENDED",
      "AWAITING_APPROVAL",
    ]);
  });

  it("maps case type, failure category and search", () => {
    const params = paramsOf(
      buildRecoveryCasesQuery(
        {
          ...EMPTY_FILTERS,
          caseType: "PAYMENT_FAILURE",
          failureCategory: "PAYMENT_RAIL_DOWNTIME",
          search: "Acme",
        },
        PAGE,
      ),
    );

    expect(params.get("case_type")).toBe("PAYMENT_FAILURE");
    expect(params.get("failure_category")).toBe("PAYMENT_RAIL_DOWNTIME");
    expect(params.get("search")).toBe("Acme");
  });

  it("trims search and omits it when only whitespace", () => {
    expect(
      paramsOf(
        buildRecoveryCasesQuery({ ...EMPTY_FILTERS, search: "  Acme  " }, PAGE),
      ).get("search"),
    ).toBe("Acme");

    expect(
      paramsOf(
        buildRecoveryCasesQuery({ ...EMPTY_FILTERS, search: "   " }, PAGE),
      ).has("search"),
    ).toBe(false);
  });

  it("converts the minimum amount filter to minor units", () => {
    expect(
      paramsOf(
        buildRecoveryCasesQuery(
          { ...EMPTY_FILTERS, minAmountMajor: "4999" },
          PAGE,
        ),
      ).get("min_amount_minor"),
    ).toBe("499900");
  });

  it("omits an invalid minimum amount rather than sending a bad value", () => {
    for (const invalid of ["12.50", "abc", "-5"]) {
      expect(
        paramsOf(
          buildRecoveryCasesQuery(
            { ...EMPTY_FILTERS, minAmountMajor: invalid },
            PAGE,
          ),
        ).has("min_amount_minor"),
      ).toBe(false);
    }
  });

  it("passes the selected sort through", () => {
    expect(
      paramsOf(
        buildRecoveryCasesQuery({ ...EMPTY_FILTERS, sort: "amount_desc" }, PAGE),
      ).get("sort"),
    ).toBe("amount_desc");
  });

  it("emits pagination values from the requested page", () => {
    const params = paramsOf(
      buildRecoveryCasesQuery(EMPTY_FILTERS, { limit: 25, offset: 50 }),
    );

    expect(params.get("limit")).toBe("25");
    expect(params.get("offset")).toBe("50");
  });

  it("never emits an undocumented parameter", () => {
    const params = paramsOf(
      buildRecoveryCasesQuery(
        {
          statuses: ["FAILED"],
          caseType: "PAYMENT_FAILURE",
          failureCategory: "UNKNOWN",
          minAmountMajor: "100",
          search: "acme",
          sort: "opened_desc",
        },
        PAGE,
      ),
    );

    const documented = new Set([
      "status",
      "case_type",
      "failure_category",
      "min_amount_minor",
      "max_amount_minor",
      "min_confidence",
      "customer_id",
      "search",
      "sort",
      "limit",
      "offset",
    ]);

    for (const key of params.keys()) {
      expect(documented.has(key)).toBe(true);
    }
  });
});

describe("hasActiveFilters", () => {
  it("is false for the default filter state", () => {
    expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false);
  });

  it("ignores sort, which always has a value", () => {
    expect(hasActiveFilters({ ...EMPTY_FILTERS, sort: "amount_desc" })).toBe(false);
  });

  it("is true once any narrowing filter is applied", () => {
    expect(hasActiveFilters({ ...EMPTY_FILTERS, statuses: ["FAILED"] })).toBe(true);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, search: "acme" })).toBe(true);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, minAmountMajor: "10" })).toBe(true);
    expect(hasActiveFilters({ ...EMPTY_FILTERS, caseType: "PAYMENT_FAILURE" })).toBe(
      true,
    );
  });
});

describe("mergeObservedOptions", () => {
  it("collects distinct non-null values in sorted order", () => {
    expect(mergeObservedOptions([], ["B", "A", "B", null])).toEqual(["A", "B"]);
  });

  it("returns the same reference when nothing new appears", () => {
    const previous = ["A", "B"];
    expect(mergeObservedOptions(previous, ["A", null, undefined])).toBe(previous);
  });

  it("ignores blank values", () => {
    expect(mergeObservedOptions([], ["   ", ""])).toEqual([]);
  });
});
