export type AppMode = "demo";

const ALLOWED_APP_MODES: readonly AppMode[] = ["demo"];

function normalizeBaseUrl(raw: string | undefined): string {
  const fallback = "http://localhost:8000";
  const value = (raw ?? fallback).trim();
  if (!value) {
    return fallback;
  }
  if (/^javascript:/i.test(value)) {
    throw new Error("Invalid API base URL.");
  }
  if (value.includes("@")) {
    throw new Error("API base URL must not embed credentials.");
  }
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("Invalid API base URL.");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("API base URL must use HTTP or HTTPS.");
  }
  return parsed.toString().replace(/\/$/, "");
}

export function getApiBaseUrl(): string {
  return normalizeBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL);
}

export function getAppMode(): AppMode {
  const raw = (process.env.NEXT_PUBLIC_APP_MODE ?? "demo").trim().toLowerCase();
  if ((ALLOWED_APP_MODES as readonly string[]).includes(raw)) {
    return raw as AppMode;
  }
  return "demo";
}

export const ENVIRONMENT_BADGE_TEXT = "DEMO / RAZORPAY TEST MODE";

export const API_REQUEST_TIMEOUT_MS = 15_000;

/**
 * Supabase project config. Both are safe to expose to the browser by
 * Supabase's own design -- the anon key is meant to be public and carries no
 * access on its own -- but here they're used only for Auth (sign-in/session),
 * never for direct data access, since RevLoop's domain data goes through the
 * FastAPI backend, not PostgREST.
 *
 * When either is unset (local/dev/test), Supabase auth is disabled and the
 * app falls back to the DevAccessTokenProvider / NEXT_PUBLIC_DEV_AUTH_TOKEN
 * path unchanged -- see lib/auth/token-provider.ts and lib/auth/session.tsx.
 */
export function getSupabaseUrl(): string | null {
  const value = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  return value ? value : null;
}

export function getSupabaseAnonKey(): string | null {
  const value = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  return value ? value : null;
}

export function isSupabaseConfigured(): boolean {
  return getSupabaseUrl() !== null && getSupabaseAnonKey() !== null;
}

export interface DemoLoginCredentials {
  email: string;
  password: string;
}

/**
 * A pre-provisioned demo account's credentials, for a one-click "Continue as
 * demo" button on /login -- judges/reviewers get a real, verified Supabase
 * session without typing anything.
 *
 * Inlined into the browser bundle like NEXT_PUBLIC_DEV_AUTH_TOKEN was, and
 * carries the same disclosed tradeoff: anyone who opens the deployed site
 * can extract this password and sign in as this account. Only provision an
 * account for this that is scoped to demo/synthetic data you're comfortable
 * being public -- never a real customer or personal account.
 */
export function getDemoLoginCredentials(): DemoLoginCredentials | null {
  if (!isSupabaseConfigured()) {
    return null;
  }
  const email = process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL?.trim();
  const password = process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD;
  if (!email || !password) {
    return null;
  }
  return { email, password };
}
