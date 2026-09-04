import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { getSupabaseAnonKey, getSupabaseUrl, isSupabaseConfigured } from "@/lib/config/public";

let cachedClient: SupabaseClient | null = null;

/**
 * The browser Supabase client, used only for Auth (sign-in, session,
 * sign-out) -- never for direct database access. Lazily constructed and
 * cached so the whole app shares one client/session.
 *
 * Throws if Supabase isn't configured; callers must check
 * isSupabaseConfigured() first (session.tsx and token-provider.ts both do).
 */
export function getSupabaseClient(): SupabaseClient {
  const url = getSupabaseUrl();
  const anonKey = getSupabaseAnonKey();
  if (!isSupabaseConfigured() || !url || !anonKey) {
    throw new Error(
      "Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY unset).",
    );
  }
  if (!cachedClient) {
    cachedClient = createClient(url, anonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }
  return cachedClient;
}
