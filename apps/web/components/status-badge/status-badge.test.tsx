import { createElement } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
