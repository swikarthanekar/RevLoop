import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DevAccessTokenProvider,
  NullAccessTokenProvider,
  SupabaseAccessTokenProvider,
  createAccessTokenProvider,
} from "./token-provider";

const ORIGINAL = process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;
const ORIGINAL_SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ORIGINAL_SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

const getSession = vi.fn();
vi.mock("./supabase-client", () => ({
  getSupabaseClient: () => ({ auth: { getSession } }),
}));

afterEach(() => {
  if (ORIGINAL === undefined) {
    delete process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;
  } else {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = ORIGINAL;
  }
  if (ORIGINAL_SUPABASE_URL === undefined) {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
  } else {
    process.env.NEXT_PUBLIC_SUPABASE_URL = ORIGINAL_SUPABASE_URL;
  }
  if (ORIGINAL_SUPABASE_ANON_KEY === undefined) {
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  } else {
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = ORIGINAL_SUPABASE_ANON_KEY;
  }
  getSession.mockReset();
});

function configureSupabase() {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key-value";
}

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

describe("SupabaseAccessTokenProvider", () => {
  it("returns the current session's access token", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "supabase-jwt-value" } },
    });

    await expect(new SupabaseAccessTokenProvider().getAccessToken()).resolves.toBe(
      "supabase-jwt-value",
    );
  });

  it("returns null when there is no session", async () => {
    getSession.mockResolvedValue({ data: { session: null } });

    await expect(new SupabaseAccessTokenProvider().getAccessToken()).resolves.toBeNull();
  });
});

describe("createAccessTokenProvider dispatch", () => {
  it("selects SupabaseAccessTokenProvider once Supabase is configured", () => {
    configureSupabase();
    expect(createAccessTokenProvider()).toBeInstanceOf(SupabaseAccessTokenProvider);
  });

  it("selects DevAccessTokenProvider when Supabase is not configured", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    expect(createAccessTokenProvider()).toBeInstanceOf(DevAccessTokenProvider);
  });

  it("prefers Supabase even when a dev token is also set", () => {
    configureSupabase();
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "dev-admin";
    expect(createAccessTokenProvider()).toBeInstanceOf(SupabaseAccessTokenProvider);
  });
});
