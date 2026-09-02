import { describe, expect, it } from "vitest";

import {
  MoneyFormatError,
  formatMoney,
  getCurrencyFractionDigits,
  parseMinorUnits,
} from "@/lib/money/format-money";

describe("formatMoney", () => {
  it("formats INR minor units to major display", () => {
    expect(formatMoney(499900, "INR")).toBe("₹4,999.00");
  });

  it("formats zero", () => {
    expect(formatMoney(0, "INR")).toBe("₹0.00");
  });

  it("formats negative minor values", () => {
    expect(formatMoney(-250, "INR")).toBe("-₹2.50");
  });

  it("formats numeric-string minor values", () => {
    expect(formatMoney("12345", "INR")).toBe("₹123.45");
  });

  it("preserves large numeric strings beyond MAX_SAFE_INTEGER", () => {
    const largeMinor = "900719925474099150";
    const formatted = formatMoney(largeMinor, "INR");
    expect(formatted).toBe("INR 9007199254740991.50");
    expect(formatted).not.toContain("e+");
  });

  it("rejects unsafe JavaScript numbers", () => {
    expect(() => formatMoney(Number.MAX_SAFE_INTEGER + 1, "INR")).toThrow(
      MoneyFormatError,
    );
  });

  it("rejects fractional minor numeric input", () => {
    expect(() => formatMoney(12.5, "INR")).toThrow(MoneyFormatError);
  });

  it("rejects malformed numeric strings", () => {
    expect(() => formatMoney("12.50", "INR")).toThrow(MoneyFormatError);
    expect(() => formatMoney("₹4999", "INR")).toThrow(MoneyFormatError);
    expect(() => formatMoney("abc", "INR")).toThrow(MoneyFormatError);
  });

  it("rejects unsupported currency codes", () => {
    expect(() => getCurrencyFractionDigits("NOTREAL")).toThrow(MoneyFormatError);
  });

  it("parses safe integer numbers exactly", () => {
    expect(parseMinorUnits(-42)).toBe(-42n);
  });
});
