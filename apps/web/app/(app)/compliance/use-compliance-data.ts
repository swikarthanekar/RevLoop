"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiClient, createDefaultApiClient } from "@/lib/api/api-client";
import { ApiError, genericApiError } from "@/lib/api/api-error";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import type { PolicyResponse } from "@/app/(app)/compliance/compliance-types";

export const POLICY_PATH = "/api/v1/policies";

export type ComplianceState =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; policy: PolicyResponse };

interface UseComplianceDataResult {
  state: ComplianceState;
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
 * Loads the enforced merchant policy -- the same MerchantPolicy row the
 * policy engine reads for every recovery decision, read back read-only.
 *
 * @param injectedClient Optional client, used by tests to supply a stub transport.
 */
export function useComplianceData(
  injectedClient?: ApiClient,
): UseComplianceDataResult {
  const client = useMemo(
    () => injectedClient ?? createDefaultApiClient(createAccessTokenProvider()),
    [injectedClient],
  );

  const [state, setState] = useState<ComplianceState>({ status: "loading" });
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
        const policy = await client.get<PolicyResponse>(POLICY_PATH);
        if (requestIdRef.current !== requestId) {
          return;
        }
        setState({ status: "ready", policy });
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
      requestIdRef.current += 1;
    };
  }, [load]);

  const refresh = useCallback(() => {
    void load(state.status === "ready");
  }, [load, state.status]);

  return { state, isRefreshing, refresh };
}
