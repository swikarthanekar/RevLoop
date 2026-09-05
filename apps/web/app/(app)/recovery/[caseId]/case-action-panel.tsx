"use client";

import { useState } from "react";

import { ENVIRONMENT_BADGE_TEXT } from "@/lib/config/public";
import {
  formatExactTimestamp,
  humanizeEnumLabel,
} from "@/app/(app)/recovery/recovery-format";
import { CaseSection } from "@/app/(app)/recovery/[caseId]/case-section";
import { describeControlAvailability } from "@/app/(app)/recovery/[caseId]/case-presentation";
import type { CaseControls } from "@/app/(app)/recovery/[caseId]/case-presentation";
import type { MutationState } from "@/app/(app)/recovery/[caseId]/use-case-actions";
import type {
  CaseCore,
  CustomerActionResponse,
  LatestAction,
  RecommendationCandidate,
  SelectedActionPolicy,
} from "@/app/(app)/recovery/[caseId]/case-types";

interface CaseActionPanelProps {
  caseCore: CaseCore;
  latestAction: LatestAction | null;
  selectedCandidate: RecommendationCandidate | null;
  selectedActionPolicy: SelectedActionPolicy | null;
  controls: CaseControls;
  mutation: MutationState;
  customerAction: CustomerActionResponse | null;
  hasAnalysis: boolean;
  onAnalyze: () => void;
  onExecute: () => void;
  onApprove: () => void;
  onReject: (reason: string, reanalyze: boolean) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  pollExhausted: boolean;
}

const PRIMARY_BUTTON =
  "inline-flex items-center justify-center rounded-md bg-accent px-3 py-2 text-sm font-medium text-on-accent hover:bg-accent-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-50";
const SECONDARY_BUTTON =
  "inline-flex items-center justify-center rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-50";

/**
 * State-dependent action controls.
 *
 * Controls are shown according to the documented state machine, but the server
 * remains authoritative: policy eligibility and approval requirements are read
 * from the analysis payload, and any rejection from the backend wins.
 */
export function CaseActionPanel({
  caseCore,
  latestAction,
  selectedCandidate,
  selectedActionPolicy,
  controls,
  mutation,
  customerAction,
  hasAnalysis,
  onAnalyze,
  onExecute,
  onApprove,
  onReject,
  onRefresh,
  isRefreshing,
  pollExhausted,
}: CaseActionPanelProps) {
  const [rejectReason, setRejectReason] = useState("");
  const [reanalyze, setReanalyze] = useState(true);

  const isPending = mutation.status === "pending";
  const status = caseCore.status;

  // Backend-supplied policy verdict for the selected action. Never derived here.
  //
  // Two verdicts exist and they answer different questions. The candidate's
  // flags record what policy decided when the analysis ran; only
  // `selectedActionPolicy` is re-evaluated against policy as it stands now,
  // which is what the executor branches on. Describing the click therefore
  // means reading the live verdict -- reading the stored one let the panel
  // promise immediate execution for an action the executor then routed to
  // approval. The stored flags remain the audit record and are still shown
  // per-candidate in the candidates table.
  //
  // A server too old to send the live verdict falls back to the stored one,
  // which is the previous behaviour rather than silence.
  const policyBlocked = selectedActionPolicy
    ? !selectedActionPolicy.eligible
    : selectedCandidate !== null && !selectedCandidate.policy_eligible;
  const requiresApproval = selectedActionPolicy
    ? selectedActionPolicy.requires_approval
    : (selectedCandidate?.requires_approval ?? false);
  const policyReasons =
    selectedActionPolicy?.reasons ?? selectedCandidate?.policy_reasons ?? [];

  const executeDisabled =
    isPending || policyBlocked || !hasAnalysis || selectedCandidate === null;

  const paymentLinkUrl =
    customerAction?.type === "PAYMENT_LINK" ? customerAction.url : null;

  return (
    <CaseSection title="Action control" headingId="case-action-heading">
      <p className="text-sm text-ink">
        {describeControlAvailability(status)}
      </p>

      <div className="mt-4 space-y-3">
        {controls.canAnalyze ? (
          <div>
            <button
              type="button"
              onClick={onAnalyze}
              disabled={isPending}
              aria-busy={isPending && mutation.kind === "analyze"}
              className={PRIMARY_BUTTON}
            >
              {isPending && mutation.kind === "analyze"
                ? "Analyzing…"
                : "Analyze case"}
            </button>
          </div>
        ) : null}

        {controls.canExecute ? (
          <div className="space-y-2">
            {policyBlocked ? (
              <div className="rounded-md border border-warning-border bg-warning-surface p-3 text-sm text-warning-ink">
                <p className="font-medium">Blocked by policy</p>
                {policyReasons.length > 0 ? (
                  <ul className="mt-1 list-disc space-y-0.5 pl-5">
                    {policyReasons.map((reason) => (
                      <li key={reason}>{humanizeEnumLabel(reason)}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1">
                    The backend marked this action ineligible under current policy.
                  </p>
                )}
              </div>
            ) : null}

            {requiresApproval && !policyBlocked ? (
              <p className="text-sm text-ink">
                This action requires approval. Submitting creates an approval
                request rather than executing immediately.
              </p>
            ) : null}

            <button
              type="button"
              onClick={onExecute}
              disabled={executeDisabled}
              aria-busy={isPending && mutation.kind === "execute"}
              className={PRIMARY_BUTTON}
            >
              {isPending && mutation.kind === "execute"
                ? "Submitting…"
                : "Execute recovery"}
            </button>
          </div>
        ) : null}

        {controls.executeBlockedByRole ? (
          <p className="rounded-md border border-line bg-surface-hover p-3 text-sm text-ink">
            A recommendation is ready to execute, but your role cannot
            execute recovery actions. Ask an operator or admin to complete
            this action.
          </p>
        ) : null}

        {controls.approvalBlockedByRole ? (
          <p className="rounded-md border border-line bg-surface-hover p-3 text-sm text-ink">
            Pending approval. Only an admin can approve or reject this
            action.
          </p>
        ) : null}

        {controls.canApprove || controls.canReject ? (
          <div className="space-y-3 rounded-md border border-line p-3">
            <p className="text-sm text-ink">
              Approval is authorized by the backend. If your role is not
              permitted, the request is rejected server-side.
            </p>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={onApprove}
                disabled={isPending || !latestAction}
                aria-busy={isPending && mutation.kind === "approve"}
                className={PRIMARY_BUTTON}
              >
                {isPending && mutation.kind === "approve"
                  ? "Approving…"
                  : "Approve action"}
              </button>
              <button
                type="button"
                onClick={() => onReject(rejectReason.trim(), reanalyze)}
                disabled={isPending || !latestAction || !rejectReason.trim()}
                aria-busy={isPending && mutation.kind === "reject"}
                className={SECONDARY_BUTTON}
              >
                {isPending && mutation.kind === "reject"
                  ? "Rejecting…"
                  : "Reject action"}
              </button>
            </div>

            <div>
              <label
                htmlFor="case-reject-reason"
                className="block text-xs font-medium text-ink-muted"
              >
                Rejection reason (required to reject)
              </label>
              <input
                id="case-reject-reason"
                type="text"
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                className="mt-1 w-full rounded-md border border-line px-2.5 py-1.5 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
              />
            </div>

            <label className="flex items-center gap-2 text-xs text-ink">
              <input
                type="checkbox"
                checked={reanalyze}
                onChange={(event) => setReanalyze(event.target.checked)}
                className="rounded border-line"
              />
              Re-analyze alternatives after rejection
            </label>
          </div>
        ) : null}

        {status === "SCHEDULED" && latestAction?.scheduled_for ? (
          <p className="text-sm text-ink">
            Scheduled for{" "}
            <time
              dateTime={latestAction.scheduled_for}
              className="font-medium"
            >
              {formatExactTimestamp(latestAction.scheduled_for)}
            </time>
          </p>
        ) : null}

        {status === "WAITING_FOR_OUTCOME" ? (
          <div className="space-y-2">
            {latestAction?.provider_reference ? (
              <p className="text-sm text-ink">
                Provider reference:{" "}
                <span className="font-mono text-xs">
                  {latestAction.provider_reference}
                </span>
              </p>
            ) : null}

            {paymentLinkUrl ? (
              <div className="rounded-md border border-line bg-surface-hover p-3">
                <p className="text-xs font-medium text-ink">
                  Customer payment link
                </p>
                <a
                  href={paymentLinkUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 block break-all font-mono text-xs text-ink underline focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
                >
                  {paymentLinkUrl}
                </a>
                <p className="mt-1 text-[11px] text-ink-muted">
                  {ENVIRONMENT_BADGE_TEXT}
                </p>
              </div>
            ) : null}

            <button
              type="button"
              onClick={onRefresh}
              disabled={isRefreshing}
              aria-busy={isRefreshing}
              className={SECONDARY_BUTTON}
            >
              {isRefreshing ? "Refreshing…" : "Refresh status"}
            </button>

            <p className="text-xs text-ink-muted" aria-live="polite">
              {pollExhausted
                ? "Automatic status checks have stopped. Use Refresh status to check again."
                : "Automatically checking for a provider outcome every few seconds."}
            </p>
          </div>
        ) : null}

        {latestAction ? (
          <p className="border-t border-line pt-3 text-xs text-ink-muted">
            Latest action: {humanizeEnumLabel(latestAction.action_type)} ·{" "}
            {humanizeEnumLabel(latestAction.status)} · attempt{" "}
            <span className="tabular-nums">{latestAction.attempt_number}</span>
          </p>
        ) : null}
      </div>
    </CaseSection>
  );
}
