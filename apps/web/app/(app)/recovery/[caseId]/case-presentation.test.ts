import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/api-error";
import {
  describeControlAvailability,
  getCaseControls,
  isConflictError,
} from "@/app/(app)/recovery/[caseId]/case-presentation";
import { formatDurationSeconds } from "@/app/(app)/recovery/[caseId]/case-format";
import {
  isTerminalStatus,
  isTransactionSource,
} from "@/app/(app)/recovery/[caseId]/case-types";
import {
  pendingApprovalActionFixture,
  recommendedCaseFixture,
} from "@/app/(app)/recovery/[caseId]/__fixtures__/case-fixtures";

const ALL_STATUSES = [
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

describe("isTerminalStatus", () => {
  it("matches the three terminal states in STATE_MACHINE.md", () => {
    expect(isTerminalStatus("RECOVERED")).toBe(true);
    expect(isTerminalStatus("FAILED")).toBe(true);
    expect(isTerminalStatus("STOPPED")).toBe(true);
  });

  it("does not treat non-terminal states as terminal", () => {
    for (const status of ["DETECTED", "ANALYZING", "RECOMMENDED", "EXECUTING"]) {
      expect(isTerminalStatus(status)).toBe(false);
    }
  });

  it("does not treat an unknown status as terminal", () => {
    expect(isTerminalStatus("SOMETHING_NEW")).toBe(false);
  });
});

describe("getCaseControls", () => {
  it("offers analysis only from DETECTED, for any role", () => {
    for (const status of ALL_STATUSES) {
      expect(getCaseControls(status, null, "ANALYST").canAnalyze).toBe(
        status === "DETECTED",
      );
    }
  });

  it("offers execution only from RECOMMENDED, for a role permitted to execute", () => {
    for (const status of ALL_STATUSES) {
      expect(getCaseControls(status, null, "ADMIN").canExecute).toBe(
        status === "RECOMMENDED",
      );
    }
  });

  it("offers approval only from AWAITING_APPROVAL with a pending action, for ADMIN", () => {
    const controls = getCaseControls(
      "AWAITING_APPROVAL",
      pendingApprovalActionFixture,
      "ADMIN",
    );
    expect(controls.canApprove).toBe(true);
    expect(controls.canReject).toBe(true);
    expect(controls.approvalBlockedByRole).toBe(false);
  });

  it("does not offer approval when no action is attached, even for ADMIN", () => {
    const controls = getCaseControls("AWAITING_APPROVAL", null, "ADMIN");
    expect(controls.canApprove).toBe(false);
    expect(controls.canReject).toBe(false);
  });

  it("suppresses every control in terminal states regardless of role", () => {
    for (const status of ["RECOVERED", "FAILED", "STOPPED"]) {
      const controls = getCaseControls(
        status,
        pendingApprovalActionFixture,
        "ADMIN",
      );
      expect(controls).toEqual({
        canAnalyze: false,
        canExecute: false,
        canApprove: false,
        canReject: false,
        isTerminal: true,
        executeBlockedByRole: false,
        approvalBlockedByRole: false,
      });
    }
  });

  it("never offers a control for an unknown future status", () => {
    const controls = getCaseControls("SOMETHING_NEW", null, "ADMIN");
    expect(controls.canAnalyze).toBe(false);
    expect(controls.canExecute).toBe(false);
    expect(controls.canApprove).toBe(false);
    expect(controls.canReject).toBe(false);
  });

  it("defaults to no role when none is supplied, hiding role-gated controls", () => {
    const controls = getCaseControls(
      "AWAITING_APPROVAL",
      pendingApprovalActionFixture,
    );
    expect(controls.canApprove).toBe(false);
    expect(controls.canReject).toBe(false);
    expect(controls.approvalBlockedByRole).toBe(true);
  });

  it("hides Execute for ANALYST but marks it as role-blocked, not state-blocked", () => {
    const controls = getCaseControls("RECOMMENDED", null, "ANALYST");
    expect(controls.canExecute).toBe(false);
    expect(controls.executeBlockedByRole).toBe(true);
  });

  it("permits Execute for OPERATOR and ADMIN, not ANALYST, from RECOMMENDED", () => {
    expect(getCaseControls("RECOMMENDED", null, "ANALYST").canExecute).toBe(false);
    expect(getCaseControls("RECOMMENDED", null, "OPERATOR").canExecute).toBe(true);
    expect(getCaseControls("RECOMMENDED", null, "ADMIN").canExecute).toBe(true);
  });

  it("permits Approve/Reject for ADMIN only, from AWAITING_APPROVAL", () => {
    for (const role of ["ANALYST", "OPERATOR"] as const) {
      const controls = getCaseControls(
        "AWAITING_APPROVAL",
        pendingApprovalActionFixture,
        role,
      );
      expect(controls.canApprove).toBe(false);
      expect(controls.canReject).toBe(false);
      expect(controls.approvalBlockedByRole).toBe(true);
    }
    const adminControls = getCaseControls(
      "AWAITING_APPROVAL",
      pendingApprovalActionFixture,
      "ADMIN",
    );
    expect(adminControls.canApprove).toBe(true);
    expect(adminControls.canReject).toBe(true);
    expect(adminControls.approvalBlockedByRole).toBe(false);
  });

  it("never marks executeBlockedByRole/approvalBlockedByRole outside their state", () => {
    const controls = getCaseControls("SCHEDULED", null, "ANALYST");
    expect(controls.executeBlockedByRole).toBe(false);
    expect(controls.approvalBlockedByRole).toBe(false);
  });
});

describe("describeControlAvailability", () => {
  it("explains every documented state", () => {
    for (const status of ALL_STATUSES) {
      expect(describeControlAvailability(status).length).toBeGreaterThan(0);
    }
  });

  it("falls back safely for an unknown status", () => {
    expect(describeControlAvailability("SOMETHING_NEW")).toContain(
      "No recovery controls",
    );
  });
});

describe("isConflictError", () => {
  function apiError(status: number, code: string): ApiError {
    return new ApiError({ status, code, safeMessage: "conflict" });
  }

  it("treats any 409 as a conflict", () => {
    expect(isConflictError(apiError(409, "SOMETHING_ELSE"))).toBe(true);
  });

  it("treats documented stale codes as conflicts", () => {
    for (const code of [
      "STALE_CASE_VERSION",
      "INVALID_CASE_STATE",
      "CASE_ALREADY_RESOLVED",
      "ACTION_ALREADY_EXISTS",
      "ACTION_NOT_PENDING_APPROVAL",
    ]) {
      expect(isConflictError(apiError(422, code))).toBe(true);
    }
  });

  it("does not treat unrelated failures as conflicts", () => {
    expect(isConflictError(apiError(403, "ROLE_NOT_ALLOWED"))).toBe(false);
    expect(isConflictError(apiError(422, "ACTION_BLOCKED_BY_POLICY"))).toBe(false);
    expect(isConflictError(apiError(502, "PAYMENT_PROVIDER_ERROR"))).toBe(false);
  });
});

describe("isTransactionSource", () => {
  it("narrows the source union by its discriminator", () => {
    expect(isTransactionSource(recommendedCaseFixture.source)).toBe(true);
  });
});

describe("formatDurationSeconds", () => {
  it("renders compact durations", () => {
    expect(formatDurationSeconds(45)).toBe("45s");
    expect(formatDurationSeconds(3120)).toBe("52m");
    expect(formatDurationSeconds(3600)).toBe("1h");
    expect(formatDurationSeconds(5400)).toBe("1h 30m");
    expect(formatDurationSeconds(90000)).toBe("1d 1h");
  });

  it("degrades to a dash for nullable or invalid values", () => {
    expect(formatDurationSeconds(null)).toBe("—");
    expect(formatDurationSeconds(undefined)).toBe("—");
    expect(formatDurationSeconds(Number.NaN)).toBe("—");
    expect(formatDurationSeconds(-5)).toBe("—");
  });
});
