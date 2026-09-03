"use client";

import { useEffect, useState } from "react";

import { ApiClient } from "@/lib/api/api-client";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import { ENVIRONMENT_BADGE_TEXT, getApiBaseUrl } from "@/lib/config/public";

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
      className="rounded-md border border-neutral-300 bg-neutral-50 px-2 py-1 text-xs text-neutral-700"
      aria-live="polite"
    >
      {label}
    </span>
  );
}

function UserMenuPlaceholder() {
  return (
    <div className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs text-neutral-700">
      Demo operator
    </div>
  );
}

export function TopBar() {
  return (
    <header className="flex items-center justify-between border-b border-neutral-200 bg-white px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-neutral-800">Merchant demo workspace</span>
        <EnvironmentBadge />
      </div>
      <div className="flex items-center gap-3">
        <ApiHealthIndicator />
        <UserMenuPlaceholder />
      </div>
    </header>
  );
}
