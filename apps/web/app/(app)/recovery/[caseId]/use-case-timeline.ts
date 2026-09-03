"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiClient } from "@/lib/api/api-client";
import { ApiError, genericApiError } from "@/lib/api/api-error";
import { caseDetailPath } from "@/app/(app)/recovery/[caseId]/use-case-detail";
import type { TimelineEntry } from "@/app/(app)/recovery/[caseId]/case-types";

export type TimelineState =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; items: TimelineEntry[] };

export interface UseCaseTimelineResult {
  state: TimelineState;
  refresh: () => Promise<void>;
  isRefreshing: boolean;
}

export function caseTimelinePath(caseId: string): string {
  return `${caseDetailPath(caseId)}/timeline`;
}

interface TimelineResponse {
  items: TimelineEntry[];
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  return genericApiError("network", "Unable to reach the RevLoop API.");
}

/**
 * Read-only audit timeline loader.
 *
 * Deliberately has no polling of its own: Prompt 21's `useCaseDetail` owns the
 * bounded WAITING_FOR_OUTCOME poll, and a second competing loop is not
 * documented as a requirement. The timeline refreshes on mount, on an explicit
 * user refresh, and when the case detail reports a new version.
 *
 * This hook performs no mutations.
 */
export function useCaseTimeline(
  caseId: string,
  client: ApiClient,
): UseCaseTimelineResult {
  const [state, setState] = useState<TimelineState>({ status: "loading" });
  const [isRefreshing, setIsRefreshing] = useState(false);

  const requestIdRef = useRef(0);
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
    async (silent: boolean) => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;

      if (silent) {
        setIsRefreshing(true);
      } else {
        setState({ status: "loading" });
      }

      try {
        const response = await client.get<TimelineResponse>(
          caseTimelinePath(caseId),
        );
        if (requestIdRef.current !== requestId || !mountedRef.current) {
          return;
        }
        // The endpoint guarantees ascending order; entries are not reordered.
        setState({
          status: "ready",
          items: Array.isArray(response?.items) ? response.items : [],
        });
      } catch (error) {
        if (requestIdRef.current !== requestId || !mountedRef.current) {
          return;
        }
        setState({ status: "error", error: toApiError(error) });
      } finally {
        if (mountedRef.current) {
          setIsRefreshing(false);
        }
      }
    },
    [client, caseId],
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  // Silent refresh: the rendered list stays mounted so focus is never moved.
  const refresh = useCallback(() => load(true), [load]);

  return { state, refresh, isRefreshing };
}
