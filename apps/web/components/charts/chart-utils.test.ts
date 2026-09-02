import { describe, expect, it } from "vitest";

import {
  buildTicks,
  niceAxisMax,
  pickLabelIndices,
  ratioOf,
  truncateLabel,
} from "@/components/charts/chart-utils";

describe("niceAxisMax", () => {
  it("rounds up to a readable boundary", () => {
    expect(niceAxisMax(9200000)).toBe(10000000);
    expect(niceAxisMax(1)).toBe(1);
    expect(niceAxisMax(42)).toBe(50);
  });

  it("stays positive for zero and invalid input", () => {
    expect(niceAxisMax(0)).toBe(1);
    expect(niceAxisMax(-5)).toBe(1);
    expect(niceAxisMax(Number.NaN)).toBe(1);
  });
});

describe("buildTicks", () => {
  it("returns evenly spaced ticks including zero and max", () => {
    expect(buildTicks(100, 4)).toEqual([0, 25, 50, 75, 100]);
  });

  it("never divides by zero for an empty dataset", () => {
    expect(buildTicks(0, 2)).toEqual([0, 0.5, 1]);
  });
});

describe("pickLabelIndices", () => {
  it("keeps every label for small datasets", () => {
    expect(pickLabelIndices(3)).toEqual([0, 1, 2]);
  });

  it("thins dense axes while keeping the first and last label", () => {
    const indices = pickLabelIndices(30, 6);
    expect(indices.length).toBeLessThanOrEqual(6);
    expect(indices[0]).toBe(0);
    expect(indices[indices.length - 1]).toBe(29);
  });

  it("returns nothing for an empty dataset", () => {
    expect(pickLabelIndices(0)).toEqual([]);
  });
});

describe("ratioOf", () => {
  it("clamps to the 0..1 range", () => {
    expect(ratioOf(50, 100)).toBe(0.5);
    expect(ratioOf(150, 100)).toBe(1);
    expect(ratioOf(-10, 100)).toBe(0);
  });

  it("returns zero when the max is zero", () => {
    expect(ratioOf(0, 0)).toBe(0);
    expect(ratioOf(5, 0)).toBe(0);
  });
});

describe("truncateLabel", () => {
  it("leaves short labels untouched", () => {
    expect(truncateLabel("Retry payment", 28)).toBe("Retry payment");
  });

  it("truncates long labels with an ellipsis", () => {
    const result = truncateLabel("Request alternate payment method immediately", 20);
    expect(result.length).toBeLessThanOrEqual(20);
    expect(result.endsWith("…")).toBe(true);
  });
});
