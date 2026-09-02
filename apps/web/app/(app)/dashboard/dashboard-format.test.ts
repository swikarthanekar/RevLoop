import { describe, expect, it } from "vitest";

import {
  formatCount,
  formatDuration,
  formatIsoDate,
  formatRate,
  formatSourceLabel,
  formatTrendDate,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/dashboard/dashboard-format";
import {
  dashboardSummaryFixture,
  emptyDashboardSummaryFixture,
} from "@/app/(app)/dashboard/__fixtures__/dashboard-fixtures";
import { isDashboardEmpty } from "@/app/(app)/dashboard/dashboard-types";
import { formatMoney } from "@/lib/money/format-money";

describe("safeMoney", () => {
  it("delegates to the central money formatter", () => {
    expect(safeMoney(499900, "INR")).toBe(formatMoney(499900, "INR"));
  });

  it("renders a dash for null and undefined", () => {
    expect(safeMoney(null, "INR")).toBe("—");
    expect(safeMoney(undefined, "INR")).toBe("—");
  });

  it("renders a dash rather than throwing on values the formatter rejects", () => {
    expect(safeMoney(12.5, "INR")).toBe("—");
    expect(safeMoney("₹4999", "INR")).toBe("—");
  });
});

describe("formatRate", () => {
  it("renders a backend 0..1 rate as a percentage", () => {
    expect(formatRate(0.655602)).toBe("65.6%");
    expect(formatRate(0)).toBe("0.0%");
    expect(formatRate(1)).toBe("100.0%");
  });

  it("renders a dash for non-finite input", () => {
    expect(formatRate(Number.NaN)).toBe("—");
  });
});

describe("formatCount", () => {
  it("groups counts for readability", () => {
    expect(formatCount(47)).toBe("47");
    expect(formatCount(0)).toBe("0");
    expect(formatCount(1234567)).toBe("12,34,567");
  });

  it("renders a dash for non-finite input", () => {
    expect(formatCount(Number.NaN)).toBe("—");
  });
});

describe("formatDuration", () => {
  it("renders null as a dash instead of a fabricated duration", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });

  it("renders seconds, minutes, hours and days", () => {
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(600)).toBe("10m");
    expect(formatDuration(5130)).toBe("1h 25m");
    expect(formatDuration(7200)).toBe("2h");
    expect(formatDuration(90000)).toBe("1d 1h");
  });
});

describe("formatTrendDate", () => {
  it("renders an ISO date as a short axis label independent of timezone", () => {
    expect(formatTrendDate("2026-08-29")).toBe("29 Aug");
    expect(formatTrendDate("2026-01-01")).toBe("1 Jan");
  });

  it("falls back to the raw value for unparseable input", () => {
    expect(formatTrendDate("not-a-date")).toBe("not-a-date");
  });
});

describe("formatIsoDate", () => {
  it("renders a timestamp as a short UTC date", () => {
    expect(formatIsoDate("2026-08-30T08:20:00Z")).toBe("30 Aug 2026");
  });
});

describe("humanizeEnumLabel", () => {
  it("turns backend enums into sentence case", () => {
    expect(humanizeEnumLabel("REQUEST_ALTERNATE_PAYMENT_METHOD")).toBe(
      "Request alternate payment method",
    );
    expect(humanizeEnumLabel("HIGH_VALUE")).toBe("High value");
  });

  it("degrades safely for empty input", () => {
    expect(humanizeEnumLabel("   ")).toBe("Unknown");
  });
});

describe("formatSourceLabel", () => {
  it("maps the synthetic demo label to the documented provenance line", () => {
    expect(formatSourceLabel("SYNTHETIC_DEMO")).toBe(
      "Synthetic batch + Razorpay Test Mode",
    );
  });

  it("never claims production for an unknown label", () => {
    expect(formatSourceLabel("SOME_NEW_SOURCE")).toBe("Some new source");
  });
});

describe("isDashboardEmpty", () => {
  it("is true only when the backend reports no money and no cases", () => {
    expect(isDashboardEmpty(emptyDashboardSummaryFixture)).toBe(true);
    expect(isDashboardEmpty(dashboardSummaryFixture)).toBe(false);
  });

  it("is false when any activity exists", () => {
    expect(
      isDashboardEmpty({ ...emptyDashboardSummaryFixture, active_cases: 1 }),
    ).toBe(false);
    expect(
      isDashboardEmpty({
        ...emptyDashboardSummaryFixture,
        revenue_at_risk_minor: 100,
      }),
    ).toBe(false);
  });
});
