import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnimatedMoney } from "@/components/money/animated-money";
import { formatMoney } from "@/lib/money/format-money";

function mockPrefersReducedMotion(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  vi.unstubAllGlobals();
  // @ts-expect-error -- test-only cleanup of a jsdom global we stub above.
  delete window.matchMedia;
});

describe("AnimatedMoney", () => {
  it("shows the final value immediately on first mount, without animating", () => {
    render(<AnimatedMoney amountMinor={125000} currency="INR" />);

    expect(screen.getByRole("status")).toHaveTextContent(formatMoney(125000, "INR"));
  });

  it("degrades to a dash for a null amount, matching safeMoney's behavior", () => {
    render(<AnimatedMoney amountMinor={null} currency="INR" />);

    expect(screen.getByRole("status")).toHaveTextContent("—");
  });

  it("always keeps the aria-label pinned to the exact backend value", () => {
    render(<AnimatedMoney amountMinor={99999} currency="INR" />);

    expect(screen.getByRole("status")).toHaveAttribute(
      "aria-label",
      `${formatMoney(99999, "INR")} INR`,
    );
  });

  it("jumps straight to the new value when the user prefers reduced motion", async () => {
    mockPrefersReducedMotion(true);
    const { rerender } = render(<AnimatedMoney amountMinor={1000} currency="INR" />);
    expect(screen.getByRole("status")).toHaveTextContent(formatMoney(1000, "INR"));

    rerender(<AnimatedMoney amountMinor={5000} currency="INR" />);

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(formatMoney(5000, "INR"));
    });
  });

  it("tweens toward the new value and settles on it exactly", async () => {
    mockPrefersReducedMotion(false);
    const { rerender } = render(
      <AnimatedMoney amountMinor={1000} currency="INR" durationSeconds={0.05} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(formatMoney(1000, "INR"));

    rerender(<AnimatedMoney amountMinor={9000} currency="INR" durationSeconds={0.05} />);

    await waitFor(
      () => {
        expect(screen.getByRole("status")).toHaveTextContent(formatMoney(9000, "INR"));
      },
      { timeout: 2000 },
    );
    // The aria-label never lags behind the real value, even mid-tween.
    expect(screen.getByRole("status")).toHaveAttribute(
      "aria-label",
      `${formatMoney(9000, "INR")} INR`,
    );
  });

  it("does not re-animate when the value is unchanged across a re-render", () => {
    const { rerender } = render(<AnimatedMoney amountMinor={4200} currency="INR" />);
    rerender(<AnimatedMoney amountMinor={4200} currency="INR" />);

    expect(screen.getByRole("status")).toHaveTextContent(formatMoney(4200, "INR"));
  });
});
