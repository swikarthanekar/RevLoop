import { ApiError } from "@/lib/api/api-error";
import {
  canApproveActions,
  canExecuteActions,
  type UserRole,
} from "@/lib/auth/role";
import {
  isTerminalStatus,
  type LatestAction,
} from "@/app/(app)/recovery/[caseId]/case-types";

/**
 * Which controls this view offers for a given backend status and role.
 *
 * IMPORTANT: this is presentation only. It exists so the UI does not show a
 * control that STATE_MACHINE.md documents as impossible, or that the
 * backend's role check (FRONTEND_SPEC.md section 6.E) will always reject for
 * the current user. It is NOT an authorization or eligibility decision:
 *
 *  - the backend re-validates every mutation, role included, and its
 *    rejection always wins;
 *  - nothing here computes policy eligibility, ERV, probability or approval
 *    requirement — those are read verbatim from the analysis payload;
 *  - a control being visible never implies the server will permit it.
 */
export interface CaseControls {
  canAnalyze: boolean;
  canExecute: boolean;
  canApprove: boolean;
  canReject: boolean;
  isTerminal: boolean;
  /** State allows execution, but the current role does not (UI messaging only). */
  executeBlockedByRole: boolean;
  /** State allows approval, but the current role is not ADMIN (UI messaging only). */
  approvalBlockedByRole: boolean;
}

/**
 * Manual analysis is offered only from `DETECTED`.
 *
 * STATE_MACHINE.md section 3 lists exactly one operator-triggered edge into
 * `ANALYZING` (`DETECTED -> ANALYZING / ANALYSIS_REQUESTED`). The other inbound
 * edges are system-triggered (schedule timer, execution failure, outcome
 * timeout) or happen through approval rejection with `reanalyze`, so no manual
 * Analyze control is offered for them. Notably there is no
 * `RECOMMENDED -> ANALYZING` transition.
 */
export function getCaseControls(
  status: string,
  latestAction: LatestAction | null,
  role: UserRole | null = null,
): CaseControls {
  const isTerminal = isTerminalStatus(status);

  if (isTerminal) {
    return {
      canAnalyze: false,
      canExecute: false,
      canApprove: false,
      canReject: false,
      isTerminal: true,
      executeBlockedByRole: false,
      approvalBlockedByRole: false,
    };
  }

  const awaitingApproval = status === "AWAITING_APPROVAL" && latestAction !== null;
  const stateAllowsExecute = status === "RECOMMENDED";
  const roleAllowsExecute = canExecuteActions(role);
  const roleAllowsApproval = canApproveActions(role);

  return {
    canAnalyze: status === "DETECTED",
    canExecute: stateAllowsExecute && roleAllowsExecute,
    canApprove: awaitingApproval && roleAllowsApproval,
    canReject: awaitingApproval && roleAllowsApproval,
    isTerminal: false,
    executeBlockedByRole: stateAllowsExecute && !roleAllowsExecute,
    approvalBlockedByRole: awaitingApproval && !roleAllowsApproval,
  };
}

/**
 * Short explanation of why no action control is offered, so a blocked state is
 * never silently empty. Wording follows STATE_MACHINE.md semantics.
 */
export function describeControlAvailability(status: string): string {
  switch (status) {
    case "DETECTED":
      return "This case has not been analyzed yet. Run analysis to produce a recommendation.";
    case "ANALYZING":
      return "Analysis is in progress. Controls become available once a recommendation is published.";
    case "RECOMMENDED":
      return "A recommendation is available for execution.";
    case "AWAITING_APPROVAL":
      return "The selected action needs an authorized approval before it can execute.";
    case "SCHEDULED":
      return "A future action is already scheduled. No additional execution is available.";
    case "EXECUTING":
      return "An action is currently executing. Controls are unavailable until it completes.";
    case "WAITING_FOR_OUTCOME":
      return "Awaiting provider outcome evidence. Refresh to load the latest state; do not execute again.";
    case "RECOVERED":
      return "This case is recovered. No further recovery actions are available.";
    case "FAILED":
      return "This case ended without recovery. No further recovery actions are available.";
    case "STOPPED":
      return "This case was intentionally stopped. No further recovery actions are available.";
    default:
      return "No recovery controls are available for the current case state.";
  }
}

/**
 * Backend error codes that mean "the case moved on" rather than "try again".
 *
 * API_CONTRACTS.md sections 7 and 8 document these as `409` conflicts. Any of
 * them must trigger a refetch and an explicit review step — never an automatic
 * retry of the mutation.
 */
export const CONFLICT_CODES = [
  "STALE_CASE_VERSION",
  "INVALID_CASE_STATE",
  "CASE_ALREADY_RESOLVED",
  "ACTION_ALREADY_EXISTS",
  "ACTION_NOT_PENDING_APPROVAL",
] as const;

export function isConflictError(error: ApiError): boolean {
  return error.status === 409 || (CONFLICT_CODES as readonly string[]).includes(error.code);
}
