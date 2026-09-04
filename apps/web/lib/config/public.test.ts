import { afterEach, describe, expect, it } from "vitest";

import {
  getDemoLoginCredentials,
  getSupabaseAnonKey,
  getSupabaseUrl,
  isSupabaseConfigured,
} from "./public";

const ORIGINAL_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ORIGINAL_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const ORIGINAL_DEMO_EMAIL = process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL;
const ORIGINAL_DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD;

afterEach(() => {
  if (ORIGINAL_URL === undefined) {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
  } else {
    process.env.NEXT_PUBLIC_SUPABASE_URL = ORIGINAL_URL;
  }
  if (ORIGINAL_ANON_KEY === undefined) {
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  } else {
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = ORIGINAL_ANON_KEY;
  }
  if (ORIGINAL_DEMO_EMAIL === undefined) {
    delete process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL;
  } else {
    process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL = ORIGINAL_DEMO_EMAIL;
  }
  if (ORIGINAL_DEMO_PASSWORD === undefined) {
    delete process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD;
  } else {
    process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD = ORIGINAL_DEMO_PASSWORD;
  }
});

function configureSupabase() {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key-value";
}

describe("getSupabaseUrl / getSupabaseAnonKey", () => {
  it("returns null when unset, so the dev-token path stays the default", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    expect(getSupabaseUrl()).toBeNull();
    expect(getSupabaseAnonKey()).toBeNull();
  });

  it("returns null for a blank value rather than an empty string", () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "   ";
    expect(getSupabaseUrl()).toBeNull();
  });

  it("returns the trimmed configured value", () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "  https://project.supabase.co  ";
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "  anon-key-value  ";

    expect(getSupabaseUrl()).toBe("https://project.supabase.co");
    expect(getSupabaseAnonKey()).toBe("anon-key-value");
  });
});

describe("isSupabaseConfigured", () => {
  it("requires both the URL and the anon key", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    expect(isSupabaseConfigured()).toBe(false);

    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
    expect(isSupabaseConfigured()).toBe(false);

    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key-value";
    expect(isSupabaseConfigured()).toBe(true);
  });
});

describe("getDemoLoginCredentials", () => {
  it("returns null when Supabase is not configured, even with both values set", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL = "demo@example.com";
    process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD = "demo-password";

    expect(getDemoLoginCredentials()).toBeNull();
  });

  it("returns null when Supabase is configured but the demo credentials are not", () => {
    configureSupabase();
    delete process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL;
    delete process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD;

    expect(getDemoLoginCredentials()).toBeNull();
  });

  it("returns null when only one of email/password is set", () => {
    configureSupabase();
    process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL = "demo@example.com";
    delete process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD;

    expect(getDemoLoginCredentials()).toBeNull();
  });

  it("returns the trimmed email and the exact password when both are configured", () => {
    configureSupabase();
    process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL = "  demo@example.com  ";
    process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD = "demo-password";

    expect(getDemoLoginCredentials()).toEqual({
      email: "demo@example.com",
      password: "demo-password",
    });
  });
});
