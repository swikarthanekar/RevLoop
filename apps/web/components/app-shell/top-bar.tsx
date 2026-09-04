"use client";

import { useEffect, useState } from "react";
import { LogOut } from "lucide-react";

import { ApiClient } from "@/lib/api/api-client";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import { useAuthSession } from "@/lib/auth/session";
import { ENVIRONMENT_BADGE_TEXT, getApiBaseUrl, isSupabaseConfigured } from "@/lib/config/public";

type HealthState = "unknown" | "connected" | "unavailable";

interface HealthResponse {
  status?: string;
}

function EnvironmentBadge() {
  return (
    <span className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-900">
      {ENVIRONMENT_BADGE_TEXT}
    </span>
  );
}

const HEALTH_DOT: Record<HealthState, string> = {
  unknown: "bg-neutral-400",
  connected: "bg-emerald-500",
  unavailable: "bg-rose-500",
};

function ApiHealthIndicator() {
  const [healthState, setHealthState] = useState<HealthState>("unknown");

  useEffect(() => {
    let cancelled = false;
    const client = new ApiClient({
      baseUrl: getApiBaseUrl(),
      tokenProvider: createAccessTokenProvider(),
    });

    client
      .get<HealthResponse>("/health")
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setHealthState(payload.status === "ok" ? "connected" : "unavailable");
      })
      .catch(() => {
        if (!cancelled) {
          setHealthState("unavailable");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const label =
    healthState === "connected"
      ? "API connected"
      : healthState === "unavailable"
        ? "API unavailable"
        : "Checking API";

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md border border-neutral-300 bg-neutral-50 px-2 py-1 text-xs text-neutral-700"
      aria-live="polite"
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${HEALTH_DOT[healthState]} ${
          healthState === "connected" ? "animate-pulse" : ""
        }`}
      />
      {label}
    </span>
  );
}

function UserMenu() {
  const { role, signOut } = useAuthSession();
  const [signingOut, setSigningOut] = useState(false);

  if (!isSupabaseConfigured()) {
    return (
      <div className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs text-neutral-700">
        Demo operator
      </div>
    );
  }

  const handleSignOut = async () => {
    if (signingOut) {
      return;
    }
    setSigningOut(true);
    try {
      await signOut();
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <span className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs text-neutral-700">
        {role ? roleLabel(role) : "Signed in"}
      </span>
      <button
        type="button"
        onClick={() => void handleSignOut()}
        disabled={signingOut}
        aria-busy={signingOut}
        className="inline-flex items-center gap-1.5 rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <LogOut className="h-3.5 w-3.5" aria-hidden="true" strokeWidth={2} />
        {signingOut ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );
}

function roleLabel(role: string): string {
  return role.charAt(0) + role.slice(1).toLowerCase();
}

export function TopBar() {
  return (
    <header className="flex items-center justify-between border-b border-neutral-200/80 bg-white/80 px-4 py-3 backdrop-blur-md">
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-neutral-800">Merchant demo workspace</span>
        <EnvironmentBadge />
      </div>
      <div className="flex items-center gap-3">
        <ApiHealthIndicator />
        <UserMenu />
      </div>
    </header>
  );
}
