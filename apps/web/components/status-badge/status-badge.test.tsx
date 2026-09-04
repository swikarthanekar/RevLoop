import { createElement } from "react";
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  RECOVERY_CASE_STATUS_MAP,
  type RecoveryCaseStatusValue,
} from "@/components/status-badge/mapping";
import { StatusBadge } from "@/components/status-badge/status-badge";

const ALL_STATUSES = Object.keys(
  RECOVERY_CASE_STATUS_MAP,
) as RecoveryCaseStatusValue[];

describe("StatusBadge", () => {
  it.each(ALL_STATUSES)("renders %s with readable label and tone", (status) => {
    const expected = RECOVERY_CASE_STATUS_MAP[status];
    render(createElement(StatusBadge, { status }));
    expect(screen.getByText(expected.label)).toBeInTheDocument();
    expect(screen.getByLabelText(`Status: ${expected.label}`)).toBeInTheDocument();
  });

  it("degrades unknown statuses to neutral Unknown", () => {
    render(createElement(StatusBadge, { status: "FUTURE_STATUS" }));
    const badge = screen.getByText("Unknown");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("neutral");
    expect(badge.className).not.toContain("emerald");
  });

  it("does not highlight on first mount", () => {
    render(createElement(StatusBadge, { status: "RECOVERED" }));
    const badge = screen.getByText("Recovered");
    expect(badge.className).not.toContain("scale-110");
  });

  it("briefly highlights when the status changes after mount", () => {
    vi.useFakeTimers();
    const { rerender } = render(createElement(StatusBadge, { status: "EXECUTING" }));

    rerender(createElement(StatusBadge, { status: "RECOVERED" }));

    const badge = screen.getByText("Recovered");
    expect(badge.className).toContain("scale-110");

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(badge.className).not.toContain("scale-110");
    vi.useRealTimers();
  });

  it("does not highlight when re-rendered with the same status", () => {
    const { rerender } = render(createElement(StatusBadge, { status: "EXECUTING" }));
    rerender(createElement(StatusBadge, { status: "EXECUTING" }));

    const badge = screen.getByText("Executing");
    expect(badge.className).not.toContain("scale-110");
  });

  it("skips the highlight when the user prefers reduced motion", () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: true,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })) as unknown as typeof window.matchMedia;

    const { rerender } = render(createElement(StatusBadge, { status: "EXECUTING" }));
    rerender(createElement(StatusBadge, { status: "RECOVERED" }));

    const badge = screen.getByText("Recovered");
    expect(badge.className).not.toContain("scale-110");

    // @ts-expect-error -- test-only cleanup of a jsdom global stubbed above.
    delete window.matchMedia;
  });
});
