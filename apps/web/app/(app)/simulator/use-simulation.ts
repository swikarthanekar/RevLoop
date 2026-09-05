"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiClient, createDefaultApiClient } from "@/lib/api/api-client";
import { ApiError, genericApiError } from "@/lib/api/api-error";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import type {
  SimulationRequest,
  SimulationResponse,
} from "@/app/(app)/simulator/simulator-types";

export const SIMULATE_PATH = "/api/v1/simulator/score";

/** Debounce so dragging a slider does not fire a request per pixel. */
export const SIMULATE_DEBOUNCE_MS = 250;

export type SimulationState =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: SimulationResponse };

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  return genericApiError("network", "Unable to reach the RevLoop API.");
}

/**
 * Scores a scenario server-side, re-running whenever the scenario changes.
 *
 * Two behaviours matter for how this feels while someone drags a slider:
 *
 * - responses are debounced, so a drag issues one request rather than dozens;
 * - a response is discarded if the scenario changed while it was in flight, so
 *   a slow earlier request can never overwrite a newer answer.
 *
 * The previous result stays on screen during a refresh instead of flashing a
 * skeleton, which keeps the numbers readable while a control is being moved.
 */
export function useSimulation(
  request: SimulationRequest,
  injectedClient?: ApiClient,
): { state: SimulationState; isRefreshing: boolean } {
  const client = useMemo(
    () => injectedClient ?? createDefaultApiClient(createAccessTokenProvider()),
    [injectedClient],
  );

  const [state, setState] = useState<SimulationState>({ status: "loading" });
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Serialized so the effect re-runs on value changes rather than on every
  // new object identity from the parent's render.
  const key = JSON.stringify(request);
  const latestKeyRef = useRef(key);
  latestKeyRef.current = key;

  const run = useCallback(
    (payload: SimulationRequest, issuedForKey: string) => {
      setIsRefreshing(true);
      client
        .post<SimulationResponse>(SIMULATE_PATH, payload)
        .then((data) => {
          // Ignore a response whose scenario is no longer the current one.
          if (latestKeyRef.current === issuedForKey) {
            setState({ status: "ready", data });
          }
        })
        .catch((error: unknown) => {
          if (latestKeyRef.current === issuedForKey) {
            setState({ status: "error", error: toApiError(error) });
          }
        })
        .finally(() => {
          if (latestKeyRef.current === issuedForKey) {
            setIsRefreshing(false);
          }
        });
    },
    [client],
  );

  useEffect(() => {
    const payload = JSON.parse(key) as SimulationRequest;
    const timer = setTimeout(() => run(payload, key), SIMULATE_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [key, run]);

  return { state, isRefreshing };
}
