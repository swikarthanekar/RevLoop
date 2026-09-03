import { describe, expect, it } from "vitest";

import {
  formatActorLabel,
  formatEventName,
  formatSafeEvidence,
  getEventCategory,
  isWarningEvent,
} from "@/app/(app)/recovery/[caseId]/audit-timeline-format";
import {
  SENTINELS,
  unsafeEvidenceEntry,
  wrongTypeEvidenceEntry,
} from "@/app/(app)/recovery/[caseId]/__fixtures__/timeline-fixtures";

describe("getEventCategory", () => {
  it("maps documented event types to their spec categories", () => {
    expect(getEventCategory("CASE_CREATED", "PROVIDER").label).toBe(
      "Provider event",
    );
    expect(getEventCategory("ANALYSIS_COMPLETED", "MODEL").label).toBe(
      "System analysis",
    );
    expect(getEventCategory("APPROVAL_REQUESTED", "SYSTEM").label).toBe(
      "Policy decision",
    );
    expect(getEventCategory("APPROVED_NOW", "USER").label).toBe("User approval");
    expect(getEventCategory("ACTION_EXECUTION_STARTED", "SYSTEM").label).toBe(
      "Action execution",
    );
    expect(getEventCategory("CASE_RECOVERED", "SYSTEM").label).toBe(
      "Recovery outcome",
    );
    expect(getEventCategory("STALE_WEBHOOK_IGNORED", "PROVIDER").label).toBe(
      "Warning",
    );
  });

  it("falls back to the documented actor enum for unknown event types", () => {
    // `event_type` is not a closed enum: raw provider names are stored verbatim.
    expect(getEventCategory("payment.captured", "PROVIDER").label).toBe(
      "Provider event",
    );
    expect(getEventCategory("some.future.event", "MODEL").label).toBe(
      "System analysis",
    );
    expect(getEventCategory("SOMETHING_NEW", "USER").label).toBe(
      "User approval",
    );
  });

  it("falls back to a neutral category when both fields are unknown", () => {
    expect(getEventCategory("SOMETHING_NEW", "ROBOT").label).toBe(
      "System event",
    );
    expect(getEventCategory("", "").label).toBe("System event");
  });

  it("always produces a non-empty visible label", () => {
    for (const eventType of ["CASE_CREATED", "weird.event", ""]) {
      expect(getEventCategory(eventType, "SYSTEM").label.length).toBeGreaterThan(
        0,
      );
    }
  });
});

describe("isWarningEvent", () => {
  it("marks only documented warning event types", () => {
    expect(isWarningEvent("STALE_WEBHOOK_IGNORED", "PROVIDER")).toBe(true);
    expect(isWarningEvent("TERMINAL_RECONCILIATION_REQUIRED", "PROVIDER")).toBe(
      true,
    );
  });

  it("never marks ordinary lifecycle events as warnings", () => {
    // Staleness is not inferred from age, ordering or current case status.
    for (const eventType of [
      "CASE_CREATED",
      "ANALYSIS_COMPLETED",
      "ACTION_EXECUTION_STARTED",
      "CASE_RECOVERED",
      "payment.captured",
    ]) {
      expect(isWarningEvent(eventType, "SYSTEM")).toBe(false);
    }
  });
});

describe("formatActorLabel", () => {
  it("labels the documented actor enum", () => {
    expect(formatActorLabel("SYSTEM")).toBe("System");
    expect(formatActorLabel("USER")).toBe("Operator");
    expect(formatActorLabel("PROVIDER")).toBe("Provider");
    expect(formatActorLabel("MODEL")).toBe("Model");
  });

  it("omits an unknown actor rather than inventing a label", () => {
    expect(formatActorLabel("SOMETHING_NEW")).toBeNull();
    expect(formatActorLabel("")).toBeNull();
  });
});

describe("formatEventName", () => {
  it("preserves the backend event type verbatim", () => {
    expect(formatEventName("ANALYSIS_COMPLETED")).toBe("ANALYSIS_COMPLETED");
    expect(formatEventName("payment.captured")).toBe("payment.captured");
  });

  it("degrades safely for a blank event type", () => {
    expect(formatEventName("")).toBe("UNKNOWN_EVENT");
    expect(formatEventName("   ")).toBe("UNKNOWN_EVENT");
  });
});

describe("formatSafeEvidence — allowlist", () => {
  it("renders documented safe fields with human labels", () => {
    const items = formatSafeEvidence({
      failure_category: "PAYMENT_RAIL_DOWNTIME",
      selected_action: "CREATE_PAYMENT_LINK",
      provider_event_id: "evt_ABC123",
    });

    expect(items).toEqual([
      {
        key: "failure_category",
        label: "Failure category",
        value: "Payment rail downtime",
        mono: false,
      },
      {
        key: "selected_action",
        label: "Selected action",
        value: "Create payment link",
        mono: false,
      },
      {
        key: "provider_event_id",
        label: "Provider event",
        value: "evt_ABC123",
        mono: true,
      },
    ]);
  });

  it("renders a documented string list", () => {
    const items = formatSafeEvidence({
      policy_reasons: ["AMOUNT_ABOVE_AUTO_ACTION_LIMIT", "HIGH_VALUE_CUSTOMER"],
    });
    expect(items).toHaveLength(1);
    expect(items[0].value).toBe(
      "Amount above auto action limit, High value customer",
    );
  });

  it("renders numeric case versions", () => {
    const items = formatSafeEvidence({ previous_version: 4, new_version: 5 });
    expect(items.map((item) => item.value)).toEqual(["4", "5"]);
  });

  it("uses a deterministic order regardless of backend key order", () => {
    const forward = formatSafeEvidence({
      failure_category: "A_B",
      analysis_run_id: "run-1",
    });
    const reversed = formatSafeEvidence({
      analysis_run_id: "run-1",
      failure_category: "A_B",
    });
    expect(forward.map((i) => i.key)).toEqual(reversed.map((i) => i.key));
  });

  it("drops every key outside the allowlist", () => {
    const items = formatSafeEvidence(unsafeEvidenceEntry.evidence);

    expect(items.map((item) => item.key).sort()).toEqual([
      "analysis_run_id",
      "failure_category",
    ]);

    const serialized = JSON.stringify(items);
    for (const sentinel of Object.values(SENTINELS)) {
      expect(serialized).not.toContain(sentinel);
    }
  });

  it("drops allowlisted keys holding the wrong type", () => {
    // A known key name must not become a channel for an arbitrary payload.
    expect(formatSafeEvidence(wrongTypeEvidenceEntry.evidence)).toEqual([]);
  });

  it("drops an allowlisted list containing non-string members", () => {
    expect(
      formatSafeEvidence({ policy_reasons: ["OK_REASON", { leak: "x" }] }),
    ).toEqual([]);
  });

  it("drops an over-long reference that is really a payload", () => {
    expect(
      formatSafeEvidence({ payment_id: "x".repeat(200) }),
    ).toEqual([]);
  });

  it("drops a reference containing control characters", () => {
    expect(
      formatSafeEvidence({ payment_id: "pay_1\nAuthorization: Bearer leak" }),
    ).toEqual([]);
  });

  it("drops a reference that is prose rather than an identifier", () => {
    // Validating the value shape stops an allowlisted key printing free text.
    expect(
      formatSafeEvidence({
        payment_id: "Traceback (most recent call last): psycopg2.Error",
      }),
    ).toEqual([]);
    expect(
      formatSafeEvidence({ analysis_run_id: "contact me at a@b.com" }),
    ).toEqual([]);
  });

  it("accepts genuine identifier shapes", () => {
    expect(
      formatSafeEvidence({
        analysis_run_id: "55555555-5555-4555-8555-555555555555",
        provider_event_id: "evt_TESTPROVIDER01",
        payment_id: "pay_TESTRECOVERED",
        source_event_key: "payment.failed:pay_123",
      }),
    ).toHaveLength(4);
  });

  it("caps a long allowlisted list", () => {
    const items = formatSafeEvidence({
      policy_reasons: ["A", "B", "C", "D", "E", "F", "G", "H"],
    });
    expect(items[0].value.split(", ")).toHaveLength(6);
  });

  it("returns nothing for empty, missing or non-object evidence", () => {
    expect(formatSafeEvidence({})).toEqual([]);
    expect(formatSafeEvidence(null)).toEqual([]);
    expect(formatSafeEvidence(undefined)).toEqual([]);
    expect(formatSafeEvidence("a string")).toEqual([]);
    expect(formatSafeEvidence([{ failure_category: "X" }])).toEqual([]);
  });

  it("ignores inherited prototype properties", () => {
    const hostile = Object.create({ failure_category: "INHERITED_LEAK" });
    expect(formatSafeEvidence(hostile)).toEqual([]);
  });
});
