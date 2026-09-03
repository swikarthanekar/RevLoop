"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiClient, createDefaultApiClient } from "@/lib/api/api-client";
import { ApiError, genericApiError } from "@/lib/api/api-error";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import type { CaseDetail } from "@/app/(app)/recovery/[caseId]/case-types";

/** Bounded polling policy for WAITING_FOR_OUTCOME (4s, within the 3–5s band). */
export const POLL_INTERVAL_MS = 4000;

/** 15 attempts ≈ 60s, after which the user falls back to manual Refresh. */
export const MAX_POLL_ATTEMPTS = 15;

export type CaseDetailState =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: CaseDetail };

export interface UseCaseDetailResult {
  state: CaseDetailState;
  /** Foreground refetch: shows the skeleton. */
  refresh: () => Promise<void>;
  /** Background refetch: leaves the rendered UI (and focus) in place. */
  refreshSilently: () => Promise<void>;
  isRefreshing: boolean;
  pollAttempts: number;
  pollExhausted: boolean;
}

export function caseDetailPath(caseId: string): string {
  return `/api/v1/recovery-cases/${encodeURIComponent(caseId)}`;
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  return genericApiError("network", "Unable to reach the RevLoop API.");
}

/**
 * Loads authoritative case detail and keeps it fresh.
 *
 * While the backend reports `WAITING_FOR_OUTCOME` this polls the read endpoint
 * on a bounded schedule. Polling never repeats a mutation — it only refetches
 * authoritative state — and stops as soon as the status changes, the attempt
 * budget is spent, or the component unmounts.
 */
export function useCaseDetail(
  caseId: string,
  injectedClient?: ApiClient,
): UseCaseDetailResult {
  const client = useMemo(
    () => injectedClient ?? createDefaultApiClient(createAccessTokenProvider()),
    [injectedClient],
  );

  const [state, setState] = useState<CaseDetailState>({ status: "loading" });
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pollAttempts, setPollAttempts] = useState(0);

  const requestIdRef = useRef(0);
  const inFlightRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      // Invalidate any in-flight response so it cannot set state after unmount.
      requestIdRef.current += 1;
    };
  }, []);

  const load = useCallback(
    async (options: { silent?: boolean; skipIfBusy?: boolean } = {}) => {
      const { silent = false, skipIfBusy = false } = options;

      // Prevents overlapping poll requests.
      if (skipIfBusy && inFlightRef.current) {
        return;
      }

      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      inFlightRef.current = true;

      if (silent) {
        setIsRefreshing(true);
      } else {
        setState({ status: "loading" });
      }

      try {
        const data = await client.get<CaseDetail>(caseDetailPath(caseId));
        if (requestIdRef.current !== requestId || !mountedRef.current) {
          return;
        }
        setState({ status: "ready", data });
      } catch (error) {
        if (requestIdRef.current !== requestId || !mountedRef.current) {
          return;
        }
        const apiError = toApiError(error);
        if (apiError.status === 404 || apiError.code === "CASE_NOT_FOUND") {
          setState({ status: "not-found" });
        } else {
          setState({ status: "error", error: apiError });
        }
      } finally {
        inFlightRef.current = false;
        if (mountedRef.current) {
          setIsRefreshing(false);
        }
      }
    },
    [client, caseId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const waitingForOutcome =
    state.status === "ready" && state.data.case.status === "WAITING_FOR_OUTCOME";

  // Reset the attempt budget whenever the case leaves WAITING_FOR_OUTCOME, so a
  // case that returns to it later gets a fresh budget.
  useEffect(() => {
    if (!waitingForOutcome) {
      setPollAttempts(0);
    }
  }, [waitingForOutcome]);

  useEffect(() => {
    if (!waitingForOutcome || pollAttempts >= MAX_POLL_ATTEMPTS) {
      return;
    }

    const timer = setTimeout(() => {
      setPollAttempts((attempts) => attempts + 1);
      void load({ silent: true, skipIfBusy: true });
    }, POLL_INTERVAL_MS);

    return () => clearTimeout(timer);
  }, [waitingForOutcome, pollAttempts, state, load]);

  const refresh = useCallback(() => load(), [load]);
  const refreshSilently = useCallback(() => load({ silent: true }), [load]);

  return {
    state,
    refresh,
    refreshSilently,
    isRefreshing,
    pollAttempts,
    pollExhausted: waitingForOutcome && pollAttempts >= MAX_POLL_ATTEMPTS,
  };
}
