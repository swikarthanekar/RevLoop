"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiClient } from "@/lib/api/api-client";
import { ApiError, genericApiError } from "@/lib/api/api-error";
import { isConflictError } from "@/app/(app)/recovery/[caseId]/case-presentation";
import { caseDetailPath } from "@/app/(app)/recovery/[caseId]/use-case-detail";
import type {
  CreateRecoveryActionResponse,
  CustomerActionResponse,
  RecoveryActionType,
} from "@/app/(app)/recovery/[caseId]/case-types";

export type MutationKind = "analyze" | "execute" | "approve" | "reject";

export type MutationState =
  | { status: "idle" }
  | { status: "pending"; kind: MutationKind }
  | { status: "error"; kind: MutationKind; error: ApiError; conflict: boolean };

export interface UseCaseActionsOptions {
  caseId: string;
  client: ApiClient;
  /** Refetches authoritative case state after a success or a conflict. */
  onAuthoritativeRefetch: () => Promise<void>;
}

export interface UseCaseActionsResult {
  mutation: MutationState;
  /**
   * Payment link (or other customer action) returned by the create-action
   * response. Held here because the case-detail contract does not expose it.
   */
  customerAction: CustomerActionResponse | null;
  analyze: () => Promise<void>;
  execute: (analysisRunId: string, actionType: RecoveryActionType) => Promise<void>;
  approve: (actionId: string, expectedCaseVersion: number) => Promise<void>;
  reject: (actionId: string, reason: string, reanalyze: boolean) => Promise<void>;
  dismissError: () => void;
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  return genericApiError("network", "Unable to reach the RevLoop API.");
}

/**
 * Mutations for the case detail screen.
 *
 * Invariants:
 *  - one mutation at a time; a pending request blocks duplicate submission;
 *  - nothing is applied optimistically — the UI only changes after the server
 *    state is refetched;
 *  - a conflict (409 / documented stale codes) refetches authoritative state and
 *    surfaces a review prompt, and never automatically repeats the mutation.
 */
export function useCaseActions({
  caseId,
  client,
  onAuthoritativeRefetch,
}: UseCaseActionsOptions): UseCaseActionsResult {
  const [mutation, setMutation] = useState<MutationState>({ status: "idle" });
  const [customerAction, setCustomerAction] =
    useState<CustomerActionResponse | null>(null);

  const busyRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const run = useCallback(
    async (kind: MutationKind, request: () => Promise<unknown>) => {
      // Ref guard rather than state, because state updates are asynchronous and
      // a fast double click would otherwise submit twice.
      if (busyRef.current) {
        return;
      }
      busyRef.current = true;
      setMutation({ status: "pending", kind });

      try {
        const result = await request();

        if (kind === "execute") {
          const created = result as CreateRecoveryActionResponse;
          if (mountedRef.current && created?.customer_action) {
            setCustomerAction(created.customer_action);
          }
        }

        if (mountedRef.current) {
          setMutation({ status: "idle" });
        }
        await onAuthoritativeRefetch();
      } catch (error) {
        const apiError = toApiError(error);
        const conflict = isConflictError(apiError);

        if (mountedRef.current) {
          setMutation({ status: "error", kind, error: apiError, conflict });
        }

        if (conflict) {
          // Load the state the server actually holds. The mutation is NOT retried.
          await onAuthoritativeRefetch();
        }
      } finally {
        busyRef.current = false;
      }
    },
    [onAuthoritativeRefetch],
  );

  const analyze = useCallback(
    () =>
      run("analyze", () =>
        client.post(`${caseDetailPath(caseId)}/analyze`, {
          reason: "MANUAL_ANALYSIS",
        }),
      ),
    [run, client, caseId],
  );

  const execute = useCallback(
    (analysisRunId: string, actionType: RecoveryActionType) =>
      run("execute", () =>
        client.post<CreateRecoveryActionResponse>(
          `${caseDetailPath(caseId)}/actions`,
          { analysis_run_id: analysisRunId, action_type: actionType },
        ),
      ),
    [run, client, caseId],
  );

  const approve = useCallback(
    (actionId: string, expectedCaseVersion: number) =>
      run("approve", () =>
        client.post(
          `/api/v1/recovery-actions/${encodeURIComponent(actionId)}/approve`,
          { expected_case_version: expectedCaseVersion },
        ),
      ),
    [run, client],
  );

  const reject = useCallback(
    (actionId: string, reason: string, reanalyze: boolean) =>
      run("reject", () =>
        client.post(
          `/api/v1/recovery-actions/${encodeURIComponent(actionId)}/reject`,
          { reason, reanalyze },
        ),
      ),
    [run, client],
  );

  const dismissError = useCallback(() => setMutation({ status: "idle" }), []);

  return {
    mutation,
    customerAction,
    analyze,
    execute,
    approve,
    reject,
    dismissError,
  };
}
