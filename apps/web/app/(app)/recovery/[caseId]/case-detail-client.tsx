"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import Link from "next/link";

import { EmptyState, ErrorState } from "@/components/async-state/error-state";
import { ApiClient, createDefaultApiClient } from "@/lib/api/api-client";
import { createAccessTokenProvider } from "@/lib/auth/token-provider";
import { useAuthSession } from "@/lib/auth/session";
import { CaseActionPanel } from "@/app/(app)/recovery/[caseId]/case-action-panel";
import { CaseCandidatesTable } from "@/app/(app)/recovery/[caseId]/case-candidates-table";
import { CaseDecisionCard } from "@/app/(app)/recovery/[caseId]/case-decision-card";
import { CaseFailureCard } from "@/app/(app)/recovery/[caseId]/case-failure-card";
import { CaseHeader } from "@/app/(app)/recovery/[caseId]/case-header";
import { CaseMutationBanner } from "@/app/(app)/recovery/[caseId]/case-mutation-banner";
import { CaseOutcomeCard } from "@/app/(app)/recovery/[caseId]/case-outcome-card";
import { CaseDetailSkeleton } from "@/app/(app)/recovery/[caseId]/case-skeleton";
import { getCaseControls } from "@/app/(app)/recovery/[caseId]/case-presentation";
import { isTerminalStatus } from "@/app/(app)/recovery/[caseId]/case-types";
import { useCaseActions } from "@/app/(app)/recovery/[caseId]/use-case-actions";
import { useCaseDetail } from "@/app/(app)/recovery/[caseId]/use-case-detail";
import { AuditTimeline } from "@/app/(app)/recovery/[caseId]/audit-timeline";
import { useCaseTimeline } from "@/app/(app)/recovery/[caseId]/use-case-timeline";

interface CaseDetailClientProps {
  caseId: string;
  /** Optional client injection seam used by tests. */
  apiClient?: ApiClient;
}

/**
 * Recovery Case Detail.
 *
 * The server owns case state, policy eligibility, approval requirements and
 * outcomes. This component renders what the backend returned, submits documented
 * mutations, and refetches authoritative state afterwards. It never applies a
 * transition optimistically.
 */
export function CaseDetailClient({ caseId, apiClient }: CaseDetailClientProps) {
  const { role } = useAuthSession();
  const client = useMemo(
    () => apiClient ?? createDefaultApiClient(createAccessTokenProvider()),
    [apiClient],
  );

  const {
    state,
    refresh,
    refreshSilently,
    isRefreshing,
    pollExhausted,
  } = useCaseDetail(caseId, client);

  const {
    state: timelineState,
    refresh: refreshTimeline,
    isRefreshing: isTimelineRefreshing,
  } = useCaseTimeline(caseId, client);

  // Unchanged from Prompt 21: the mutation chain still awaits only the
  // case-detail fetch. The timeline is deliberately NOT awaited here, so a slow
  // or failing timeline read cannot alter mutation, conflict or polling
  // behaviour.
  const onAuthoritativeRefetch = useCallback(
    () => refreshSilently(),
    [refreshSilently],
  );

  /** User-initiated refresh covers both the case and its audit history. */
  const handleRefreshAll = useCallback(() => {
    void refresh();
    void refreshTimeline();
  }, [refresh, refreshTimeline]);

  const {
    mutation,
    customerAction,
    analyze,
    execute,
    approve,
    reject,
    dismissError,
  } = useCaseActions({ caseId, client, onAuthoritativeRefetch });

  const detail = state.status === "ready" ? state.data : null;

  const selectedCandidate = useMemo(() => {
    if (!detail?.analysis) {
      return null;
    }
    return (
      detail.analysis.candidates.find(
        (candidate) => candidate.action_type === detail.analysis?.selected_action,
      ) ?? null
    );
  }, [detail]);

  const handleExecute = useCallback(() => {
    if (!detail?.analysis || !selectedCandidate) {
      return;
    }
    void execute(
      detail.analysis.analysis_run_id,
      selectedCandidate.action_type as Parameters<typeof execute>[1],
    );
  }, [detail, selectedCandidate, execute]);

  const handleApprove = useCallback(() => {
    if (!detail?.latest_action) {
      return;
    }
    void approve(detail.latest_action.id, detail.case.version);
  }, [detail, approve]);

  const handleReject = useCallback(
    (reason: string, reanalyze: boolean) => {
      if (!detail?.latest_action) {
        return;
      }
      void reject(detail.latest_action.id, reason, reanalyze);
    },
    [detail, reject],
  );

  // A new case version means the backend recorded new audit events, so the
  // timeline is refetched. This watches authoritative state rather than hooking
  // into the mutation path, which also covers transitions discovered by the
  // WAITING_FOR_OUTCOME poll.
  const caseVersion = detail?.case.version ?? null;
  const lastSeenVersionRef = useRef<number | null>(null);

  useEffect(() => {
    if (caseVersion === null) {
      return;
    }
    const previousVersion = lastSeenVersionRef.current;
    lastSeenVersionRef.current = caseVersion;
    if (previousVersion !== null && previousVersion !== caseVersion) {
      void refreshTimeline();
    }
  }, [caseVersion, refreshTimeline]);

  if (state.status === "loading") {
    return <CaseDetailSkeleton />;
  }

  if (state.status === "not-found") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
          Recovery case
        </h1>
        <EmptyState
          title="Case not found or unavailable"
          description="This recovery case does not exist, or it is not available to your organization."
        />
        <Link
          href="/recovery"
          className="inline-flex items-center rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
        >
          Back to Recovery Opportunities
        </Link>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
          Recovery case
        </h1>
        <ErrorState error={state.error} onRetry={refresh} />
      </div>
    );
  }

  const { case: caseCore, customer, source, analysis, latest_action, outcome } =
    state.data;
  const controls = getCaseControls(caseCore.status, latest_action, role);
  const terminal = isTerminalStatus(caseCore.status);
  // latest_action.customer_action is the durable source (survives a reload
  // and covers the approve path, which never returned a link at all); the
  // one-shot mutation response is a same-tick fallback for the instant after
  // an immediate execute, before the refetch it triggers has landed.
  const resolvedCustomerAction = latest_action?.customer_action ?? customerAction;

  return (
    <div className="space-y-4">
      <CaseHeader
        caseCore={caseCore}
        customer={customer}
        source={source}
        onRefresh={handleRefreshAll}
        isRefreshing={isRefreshing}
      />

      <CaseMutationBanner mutation={mutation} onDismiss={dismissError} />

      {terminal ? (
        <CaseOutcomeCard caseCore={caseCore} outcome={outcome} />
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <CaseFailureCard caseCore={caseCore} source={source} />
        <CaseDecisionCard
          analysis={analysis}
          currency={caseCore.currency}
          selectedCandidate={selectedCandidate}
        />
        {terminal ? (
          <CaseActionPanelTerminalNotice status={caseCore.status} />
        ) : (
          <CaseActionPanel
            caseCore={caseCore}
            latestAction={latest_action}
            selectedCandidate={selectedCandidate}
            controls={controls}
            mutation={mutation}
            customerAction={resolvedCustomerAction}
            hasAnalysis={analysis !== null}
            onAnalyze={() => void analyze()}
            onExecute={handleExecute}
            onApprove={handleApprove}
            onReject={handleReject}
            onRefresh={handleRefreshAll}
            isRefreshing={isRefreshing}
            pollExhausted={pollExhausted}
          />
        )}
      </div>

      <CaseCandidatesTable
        candidates={analysis?.candidates ?? []}
        currency={caseCore.currency}
        selectedAction={analysis?.selected_action ?? null}
      />

      <AuditTimeline
        state={timelineState}
        onRefresh={refreshTimeline}
        isRefreshing={isTimelineRefreshing}
      />
    </div>
  );
}

/** Terminal cases expose no mutation controls at all. */
function CaseActionPanelTerminalNotice({ status }: { status: string }) {
  return (
    <section
      aria-labelledby="case-action-heading"
      className="rounded-lg border border-neutral-200 bg-white p-4"
    >
      <h2
        id="case-action-heading"
        className="text-sm font-semibold uppercase tracking-wide text-neutral-500"
      >
        Action control
      </h2>
      <p className="mt-3 text-sm text-neutral-700">
        This case is in the terminal state {status}. No recovery actions are
        available.
      </p>
    </section>
  );
}
