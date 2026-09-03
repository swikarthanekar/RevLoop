import { afterEach, describe, expect, it } from "vitest";

import {
  DevAccessTokenProvider,
  NullAccessTokenProvider,
  createAccessTokenProvider,
} from "./token-provider";

const ORIGINAL = process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;

afterEach(() => {
  if (ORIGINAL === undefined) {
    delete process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;
  } else {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = ORIGINAL;
  }
});

describe("DevAccessTokenProvider", () => {
  it("returns the configured development token", async () => {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "dev-admin";
    await expect(new DevAccessTokenProvider().getAccessToken()).resolves.toBe("dev-admin");
  });

  it("sends nothing when the variable is unset", async () => {
    delete process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;
    await expect(new DevAccessTokenProvider().getAccessToken()).resolves.toBeNull();
  });

  it("treats a blank variable as unset so no header is sent", async () => {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "   ";
    await expect(new DevAccessTokenProvider().getAccessToken()).resolves.toBeNull();
  });

  it("matches NullAccessTokenProvider when unconfigured", async () => {
    delete process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;
    const fallback = await new NullAccessTokenProvider().getAccessToken();
    await expect(createAccessTokenProvider().getAccessToken()).resolves.toBe(fallback);
  });
});
