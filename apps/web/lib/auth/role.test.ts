import { afterEach, describe, expect, it } from "vitest";

import {
  canApproveActions,
  canExecuteActions,
  currentUserRole,
} from "./role";

const ORIGINAL = process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;

afterEach(() => {
  if (ORIGINAL === undefined) {
    delete process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;
  } else {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = ORIGINAL;
  }
});

describe("currentUserRole", () => {
  it("maps each documented dev token to its role", () => {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "dev-analyst";
    expect(currentUserRole()).toBe("ANALYST");

    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "dev-operator";
    expect(currentUserRole()).toBe("OPERATOR");

    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "dev-admin";
    expect(currentUserRole()).toBe("ADMIN");
  });

  it("returns null when the token is unset", () => {
    delete process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;
    expect(currentUserRole()).toBeNull();
  });

  it("returns null for an unrecognized token rather than guessing a role", () => {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "something-else";
    expect(currentUserRole()).toBeNull();
  });
});

describe("canExecuteActions", () => {
  it("permits only OPERATOR and ADMIN, mirroring _EXECUTE_ROLES", () => {
    expect(canExecuteActions("ANALYST")).toBe(false);
    expect(canExecuteActions("OPERATOR")).toBe(true);
    expect(canExecuteActions("ADMIN")).toBe(true);
    expect(canExecuteActions(null)).toBe(false);
  });
});

describe("canApproveActions", () => {
  it("permits only ADMIN, mirroring _APPROVAL_ROLES", () => {
    expect(canApproveActions("ANALYST")).toBe(false);
    expect(canApproveActions("OPERATOR")).toBe(false);
    expect(canApproveActions("ADMIN")).toBe(true);
    expect(canApproveActions(null)).toBe(false);
  });
});
