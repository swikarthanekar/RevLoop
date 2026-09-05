"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiClient, createDefaultApiClient } from "@/lib/api/api-client";
import { ApiError, genericApiError } from "@/lib/api/api-error";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import type { CachedEvaluation } from "@/app/(app)/proof/proof-types";

export const EVALUATION_PATH = "/api/v1/demo/evaluation";
export const RECOMPUTE_PATH = "/api/v1/demo/evaluation/recompute";

export type EvaluationState =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: CachedEvaluation };

interface UseEvaluationResult {
  state: EvaluationState;
  /** True while a recompute runs over already-rendered figures. */
  isRecomputing: boolean;
  recomputeError: ApiError | null;
  recompute: () => void;
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  return genericApiError("network", "Unable to reach the RevLoop API.");
}

/**
 * Loads the cached held-out policy evaluation, and re-runs it on demand.
 *
 * The backend caches the result because a cold run regenerates a 15,000-case
 * dataset and takes about ten seconds. A recompute failure is kept separate
 * from the load error on purpose: the figures already on screen are still
 * valid, so a failed recompute must annotate the page rather than replace it
 * with an error state.
 */
export function useEvaluation(injectedClient?: ApiClient): UseEvaluationResult {
  const client = useMemo(
    () => injectedClient ?? createDefaultApiClient(createAccessTokenProvider()),
    [injectedClient],
  );

  const [state, setState] = useState<EvaluationState>({ status: "loading" });
  const [isRecomputing, setIsRecomputing] = useState(false);
  const [recomputeError, setRecomputeError] = useState<ApiError | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    client
      .get<CachedEvaluation>(EVALUATION_PATH)
      .then((data) => {
        if (!cancelled) {
          setState({ status: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ status: "error", error: toApiError(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const recompute = useCallback(() => {
    if (isRecomputing) {
      return;
    }
    setIsRecomputing(true);
    setRecomputeError(null);
    client
      .post<CachedEvaluation>(RECOMPUTE_PATH, {})
      .then((data) => {
        if (mountedRef.current) {
          setState({ status: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (mountedRef.current) {
          setRecomputeError(toApiError(error));
        }
      })
      .finally(() => {
        if (mountedRef.current) {
          setIsRecomputing(false);
        }
      });
  }, [client, isRecomputing]);

  return { state, isRecomputing, recomputeError, recompute };
}
