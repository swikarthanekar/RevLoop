"use client";

import { useEffect, useState } from "react";

import { ApiClient } from "@/lib/api/api-client";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import { useAuthSession } from "@/lib/auth/session";
import { ENVIRONMENT_BADGE_TEXT, getApiBaseUrl, isSupabaseConfigured } from "@/lib/config/public";
import { MobileNav } from "@/components/app-shell/mobile-nav";
import { ThemeToggle } from "@/components/app-shell/theme-toggle";

type HealthState = "unknown" | "connected" | "unavailable";

interface HealthResponse {
  status?: string;
}

function EnvironmentBadge() {
  return (
    <span className="rounded-md border border-warning-border bg-warning-surface px-2 py-1 text-xs font-medium text-warning-ink">
      {ENVIRONMENT_BADGE_TEXT}
    </span>
  );
}

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
      className="rounded-md border border-line bg-surface-hover px-2 py-1 text-xs text-ink"
      aria-live="polite"
    >
      {label}
    </span>
  );
}

function UserMenu() {
  const { role, signOut } = useAuthSession();
  const [signingOut, setSigningOut] = useState(false);

  if (!isSupabaseConfigured()) {
    return (
      <div className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs text-ink">
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
      <span className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs text-ink">
        {role ? roleLabel(role) : "Signed in"}
      </span>
      <button
        type="button"
        onClick={() => void handleSignOut()}
        disabled={signingOut}
        aria-busy={signingOut}
        className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
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
    // `relative` anchors the mobile nav panel, which drops out of this header.
    // The bar wraps rather than overflowing on narrow viewports.
    <header className="relative flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <MobileNav />
        {/* The workspace label is the first thing to go on a phone; the
            environment badge is not, because a reviewer must always be able to
            see that this is demo data in Razorpay Test Mode. */}
        <span className="hidden text-sm font-medium text-ink sm:inline">
          Merchant demo workspace
        </span>
        <EnvironmentBadge />
      </div>
      <div className="flex items-center gap-2 sm:gap-3">
        {/* Health is diagnostic detail, not something a phone screen needs. */}
        <span className="hidden sm:inline">
          <ApiHealthIndicator />
        </span>
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
