import { isSupabaseConfigured } from "@/lib/config/public";
import { getSupabaseClient } from "@/lib/auth/supabase-client";

export interface AccessTokenProvider {
  getAccessToken(): Promise<string | null>;
}

export class NullAccessTokenProvider implements AccessTokenProvider {
  async getAccessToken(): Promise<string | null> {
    return null;
  }
}

/**
 * Supplies the development/demo bearer token the backend's DevAuthBackend
 * expects (`dev-analyst`, `dev-operator`, `dev-admin`).
 *
 * The token comes from `NEXT_PUBLIC_DEV_AUTH_TOKEN` and must be set explicitly.
 * When it is absent — which is the production case — this behaves exactly like
 * NullAccessTokenProvider and no Authorization header is sent, so a missing
 * variable can never silently grant a role.
 */
export class DevAccessTokenProvider implements AccessTokenProvider {
  async getAccessToken(): Promise<string | null> {
    const token = process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN?.trim();
    return token ? token : null;
  }
}

/**
 * Supplies the current Supabase session's access token, verified
 * server-side by SupabaseAuthBackend (apps/api/app/core/auth.py). Returns
 * null when there is no session, which the API client already treats as
 * "send no Authorization header" -- the backend then answers 401, and the
 * (app) route guard (lib/auth/session.tsx) is what actually gets an
 * unauthenticated user to /login.
 */
export class SupabaseAccessTokenProvider implements AccessTokenProvider {
  async getAccessToken(): Promise<string | null> {
    const { data } = await getSupabaseClient().auth.getSession();
    return data.session?.access_token ?? null;
  }
}

/** The provider the browser application uses for backend requests. */
export function createAccessTokenProvider(): AccessTokenProvider {
  if (isSupabaseConfigured()) {
    return new SupabaseAccessTokenProvider();
  }
  return new DevAccessTokenProvider();
}
