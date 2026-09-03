"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiClient, createDefaultApiClient } from "@/lib/api/api-client";
import { ApiError, genericApiError } from "@/lib/api/api-error";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import type { RecoveryCaseListResponse } from "@/app/(app)/recovery/recovery-types";

export type RecoveryCasesState =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: RecoveryCaseListResponse };

interface UseRecoveryCasesResult {
  state: RecoveryCasesState;
  refresh: () => void;
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  return genericApiError("network", "Unable to reach the RevLoop API.");
}

/**
 * Loads a page of recovery cases through the shared typed API client.
 *
 * The caller owns filter/pagination state and passes a fully built query, so
 * this hook simply refetches whenever that query changes.
 *
 * @param query Path and query string produced by `buildRecoveryCasesQuery`.
 * @param injectedClient Optional client, used by tests to supply a stub transport.
 */
export function useRecoveryCases(
  query: string,
  injectedClient?: ApiClient,
): UseRecoveryCasesResult {
  const client = useMemo(
    () => injectedClient ?? createDefaultApiClient(createAccessTokenProvider()),
    [injectedClient],
  );

  const [state, setState] = useState<RecoveryCasesState>({ status: "loading" });
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setState({ status: "loading" });

    try {
      const data = await client.get<RecoveryCaseListResponse>(query);
      if (requestIdRef.current !== requestId) {
        return;
      }
      setState({ status: "ready", data });
    } catch (error) {
      if (requestIdRef.current !== requestId) {
        return;
      }
      setState({ status: "error", error: toApiError(error) });
    }
  }, [client, query]);

  useEffect(() => {
    void load();
    return () => {
      // Invalidate in-flight responses so a stale page never overwrites a newer one.
      requestIdRef.current += 1;
    };
  }, [load]);

  return { state, refresh: load };
}
