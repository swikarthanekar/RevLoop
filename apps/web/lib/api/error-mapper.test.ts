import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/api-error";
import { mapApiError } from "@/lib/api/error-mapper";

function makeError(
  overrides: Partial<ConstructorParameters<typeof ApiError>[0]> & {
    kind?: ApiError["kind"];
  },
): ApiError {
  return new ApiError({
    status: 400,
    code: "UNKNOWN",
    safeMessage: "fallback",
    ...overrides,
  });
}

describe("mapApiError", () => {
  it.each([
    ["INVALID_CASE_STATE", "Refresh the case and review the latest status before retrying."],
    ["ACTION_BLOCKED_BY_POLICY", "Review policy constraints instead of retrying the same action."],
    ["ACTION_ALREADY_EXISTS", "Refetch the latest action details to avoid duplicate submissions."],
    ["PAYMENT_PROVIDER_ERROR", "The recovery case remains safe. Try again later or review provider status."],
    ["STALE_CASE_VERSION", "Refresh and review the latest case state before retrying."],
  ] as const)("maps backend code %s", (code, guidance) => {
    const mapped = mapApiError(makeError({ code, status: 409 }));
    expect(mapped.guidance).toBe(guidance);
    expect(mapped.message.length).toBeGreaterThan(0);
  });

  it.each([
    [401, "Authentication required"],
    [403, "Insufficient permission"],
    [404, "Resource unavailable"],
    [409, "Conflicting state"],
    [422, "Request was rejected"],
    [429, "Rate limited"],
    [500, "Service unavailable"],
  ] as const)("maps HTTP %s fallback", (status, title) => {
    const mapped = mapApiError(makeError({ status, code: "UNKNOWN" }));
    expect(mapped.title).toBe(title);
  });

  it("maps network failures", () => {
    const mapped = mapApiError(
      makeError({ kind: "network", code: "NETWORK_ERROR", status: 0 }),
    );
    expect(mapped.title).toBe("Connection problem");
  });

  it("maps timeout without raw body", () => {
    const mapped = mapApiError(
      makeError({ kind: "timeout", code: "REQUEST_TIMEOUT", status: 0 }),
    );
    expect(mapped.title).toBe("Request timed out");
    expect(mapped.message).not.toContain("stack");
  });

  it("does not expose raw HTML in user-visible message", () => {
    const mapped = mapApiError(
      makeError({ kind: "parse", code: "INVALID_RESPONSE", status: 500 }),
    );
    expect(mapped.message).not.toContain("<html>");
  });
});

describe("action-specific error codes", () => {
  it("explains a non-executable action instead of blaming the user's input", () => {
    // The production defect: this surfaced as "Validation failed — The request
    // could not be validated. Review the input and try again." on a screen
    // where the user had entered nothing.
    const presentation = mapApiError(
      new ApiError({
        kind: "http",
        status: 422,
        code: "ACTION_NOT_EXECUTABLE",
        safeMessage: "RevLoop does not execute RETRY_SAME_METHOD actions.",
      }),
    );

    expect(presentation.title).not.toMatch(/validation/i);
    expect(presentation.guidance).not.toMatch(/review the input/i);
    expect(presentation.message).toMatch(/RevLoop/);
  });

  it("never tells the user to review input they were never asked for", () => {
    const codes = [
      "ACTION_NOT_EXECUTABLE",
      "ACTION_NOT_IN_ANALYSIS",
      "ACTION_BLOCKED_BY_POLICY",
      "CASE_ALREADY_RESOLVED",
      "ACTION_NOT_PENDING_APPROVAL",
    ];
    for (const code of codes) {
      const presentation = mapApiError(
        new ApiError({ kind: "http", status: 422, code, safeMessage: "x" }),
      );
      expect(presentation.guidance).not.toMatch(/review the input/i);
    }
  });
});
