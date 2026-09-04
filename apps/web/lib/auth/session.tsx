"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { createDefaultApiClient } from "@/lib/api/api-client";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import { currentUserRole as devUserRole, type UserRole } from "@/lib/auth/role";
import { getSupabaseClient } from "@/lib/auth/supabase-client";
import { isSupabaseConfigured } from "@/lib/config/public";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export interface AuthSessionState {
  status: AuthStatus;
  role: UserRole | null;
  /** No-op when Supabase isn't configured -- there is no session to end. */
  signOut: () => Promise<void>;
}

interface CurrentUserResponse {
  user_id: string;
  organization_id: string;
  role: UserRole;
}

const NOOP_SIGN_OUT = async () => {};

/**
 * Dev/local/test mode: unchanged from before Supabase auth existed. Role
 * comes synchronously from NEXT_PUBLIC_DEV_AUTH_TOKEN; there is no session
 * to load, so the app never shows a loading state and the (app) route guard
 * never redirects -- each page's existing per-request 401 handling is what
 * covers an unset/invalid dev token, exactly as it did before this file
 * existed.
 */
function devModeState(): AuthSessionState {
  return { status: "authenticated", role: devUserRole(), signOut: NOOP_SIGN_OUT };
}

const AuthSessionContext = createContext<AuthSessionState | null>(null);

export function AuthSessionProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthSessionState>(() =>
    isSupabaseConfigured() ? { status: "loading", role: null, signOut: NOOP_SIGN_OUT } : devModeState(),
  );

  useEffect(() => {
    if (!isSupabaseConfigured()) {
      // No subscription needed: devModeState() is already final and correct.
      return;
    }

    let cancelled = false;
    const supabase = getSupabaseClient();

    const signOut = async () => {
      await supabase.auth.signOut();
    };

    async function resolveFromSession(hasSession: boolean) {
      if (!hasSession) {
        if (!cancelled) {
          setState({ status: "unauthenticated", role: null, signOut });
        }
        return;
      }
      try {
        const client = createDefaultApiClient(createAccessTokenProvider());
        const me = await client.get<CurrentUserResponse>("/api/v1/auth/me");
        if (!cancelled) {
          setState({ status: "authenticated", role: me.role, signOut });
        }
      } catch {
        // A session exists in the browser but the backend rejected it (e.g.
        // expired, or a Supabase account with no user_profiles row yet).
        // Treat as unauthenticated rather than looping the caller into a
        // broken "authenticated with no role" state.
        if (!cancelled) {
          setState({ status: "unauthenticated", role: null, signOut });
        }
      }
    }

    supabase.auth.getSession().then(({ data }) => {
      if (!cancelled) {
        void resolveFromSession(data.session !== null);
      }
    });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!cancelled) {
        void resolveFromSession(session !== null);
      }
    });

    return () => {
      cancelled = true;
      subscription.subscription.unsubscribe();
    };
  }, []);

  return (
    <AuthSessionContext.Provider value={state}>{children}</AuthSessionContext.Provider>
  );
}

export function useAuthSession(): AuthSessionState {
  const context = useContext(AuthSessionContext);
  if (context === null) {
    throw new Error("useAuthSession must be used within an AuthSessionProvider.");
  }
  return context;
}
