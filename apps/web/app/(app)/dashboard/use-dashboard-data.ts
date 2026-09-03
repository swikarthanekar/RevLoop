"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiClient, createDefaultApiClient } from "@/lib/api/api-client";
import { ApiError, genericApiError } from "@/lib/api/api-error";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import type {
  DashboardData,
  DashboardSummary,
  RecoveryCaseListResponse,
} from "@/app/(app)/dashboard/dashboard-types";

export const DASHBOARD_SUMMARY_PATH = "/api/v1/dashboard/summary";
export const TOP_OPPORTUNITIES_PATH =
  "/api/v1/recovery-cases?sort=priority_desc&limit=5";

export type DashboardState =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: DashboardData };

interface UseDashboardDataResult {
  state: DashboardState;
  /** True while a refresh runs over already-rendered data. */
  isRefreshing: boolean;
  refresh: () => void;
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  return genericApiError("network", "Unable to reach the RevLoop API.");
}

/**
 * Loads the Executive Dashboard through the shared typed API client.
 *
 * The summary is required: if it fails the whole dashboard reports an error.
 * Top opportunities are best-effort so a case-list outage degrades one section
 * instead of hiding the money metrics.
 *
 * @param injectedClient Optional client, used by tests to supply a stub transport.
 */
export function useDashboardData(
  injectedClient?: ApiClient,
): UseDashboardDataResult {
  const client = useMemo(
    () => injectedClient ?? createDefaultApiClient(createAccessTokenProvider()),
    [injectedClient],
  );

  const [state, setState] = useState<DashboardState>({ status: "loading" });
  const [isRefreshing, setIsRefreshing] = useState(false);
  const requestIdRef = useRef(0);

  const load = useCallback(
    async (isRefresh: boolean) => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;

      if (isRefresh) {
        setIsRefreshing(true);
      } else {
        setState({ status: "loading" });
      }

      try {
        const summary = await client.get<DashboardSummary>(DASHBOARD_SUMMARY_PATH);

        let topOpportunities: RecoveryCaseListResponse["items"] = [];
        let topOpportunitiesUnavailable = false;
        try {
          const cases = await client.get<RecoveryCaseListResponse>(
            TOP_OPPORTUNITIES_PATH,
          );
          topOpportunities = cases.items ?? [];
        } catch {
          topOpportunitiesUnavailable = true;
        }

        if (requestIdRef.current !== requestId) {
          return;
        }
        setState({
          status: "ready",
          data: { summary, topOpportunities, topOpportunitiesUnavailable },
        });
      } catch (error) {
        if (requestIdRef.current !== requestId) {
          return;
        }
        setState({ status: "error", error: toApiError(error) });
      } finally {
        if (requestIdRef.current === requestId) {
          setIsRefreshing(false);
        }
      }
    },
    [client],
  );

  useEffect(() => {
    void load(false);
    return () => {
      // Invalidate in-flight responses so an unmounted dashboard never sets state.
      requestIdRef.current += 1;
    };
  }, [load]);

  const refresh = useCallback(() => {
    void load(state.status === "ready");
  }, [load, state.status]);

  return { state, isRefreshing, refresh };
}
