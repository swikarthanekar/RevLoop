import { describe, expect, it } from "vitest";

import {
  formatCount,
  formatExactTimestamp,
  formatRate,
  formatRelativeTime,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/recovery/recovery-format";
import { formatMoney } from "@/lib/money/format-money";

describe("safeMoney", () => {
  it("delegates to the central money formatter", () => {
    expect(safeMoney(499900, "INR")).toBe(formatMoney(499900, "INR"));
  });

  it("renders a dash for nullable contract fields", () => {
    expect(safeMoney(null, "INR")).toBe("—");
    expect(safeMoney(undefined, "INR")).toBe("—");
  });

  it("renders a dash instead of throwing on rejected input", () => {
    expect(safeMoney(12.5, "INR")).toBe("—");
    expect(safeMoney("₹4999", "INR")).toBe("—");
  });
});

describe("formatRate", () => {
  it("renders a backend 0..1 probability as a percentage", () => {
    expect(formatRate(0.82)).toBe("82.0%");
    expect(formatRate(0.87, 0)).toBe("87%");
    expect(formatRate(0)).toBe("0.0%");
    expect(formatRate(1)).toBe("100.0%");
  });

  it("renders a dash for null confidence rather than zero", () => {
    expect(formatRate(null)).toBe("—");
    expect(formatRate(undefined)).toBe("—");
    expect(formatRate(Number.NaN)).toBe("—");
  });
});

describe("humanizeEnumLabel", () => {
  it("turns backend enums into sentence case", () => {
    expect(humanizeEnumLabel("PAYMENT_RAIL_DOWNTIME")).toBe("Payment rail downtime");
    expect(humanizeEnumLabel("REQUEST_ALTERNATE_PAYMENT_METHOD")).toBe(
      "Request alternate payment method",
    );
  });

  it("renders a dash for null or blank values", () => {
    expect(humanizeEnumLabel(null)).toBe("—");
    expect(humanizeEnumLabel("   ")).toBe("—");
  });
});

describe("formatRelativeTime", () => {
  const opened = "2026-08-30T08:20:00Z";
  const openedMs = Date.parse(opened);

  it("renders compact relative ages", () => {
    expect(formatRelativeTime(opened, openedMs + 30 * 1000)).toBe("just now");
    expect(formatRelativeTime(opened, openedMs + 5 * 60 * 1000)).toBe("5m ago");
    expect(formatRelativeTime(opened, openedMs + 3 * 3600 * 1000)).toBe("3h ago");
    expect(formatRelativeTime(opened, openedMs + 2 * 86400 * 1000)).toBe("2d ago");
    expect(formatRelativeTime(opened, openedMs + 60 * 86400 * 1000)).toBe("2mo ago");
    expect(formatRelativeTime(opened, openedMs + 400 * 86400 * 1000)).toBe("1y ago");
  });

  it("does not render a negative age for clock skew", () => {
    expect(formatRelativeTime(opened, openedMs - 60_000)).toBe("just now");
  });

  it("renders a dash for an unparseable timestamp", () => {
    expect(formatRelativeTime("not-a-date")).toBe("—");
  });
});

describe("formatExactTimestamp", () => {
  it("renders an exact UTC timestamp for the tooltip", () => {
    expect(formatExactTimestamp("2026-08-30T08:20:00Z")).toBe(
      "30 Aug 2026, 08:20 UTC",
    );
  });

  it("falls back to the raw value when unparseable", () => {
    expect(formatExactTimestamp("nope")).toBe("nope");
  });
});

describe("formatCount", () => {
  it("groups totals for readability", () => {
    expect(formatCount(47)).toBe("47");
    expect(formatCount(0)).toBe("0");
  });
});
