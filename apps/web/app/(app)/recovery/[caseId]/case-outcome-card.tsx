import {
  formatExactTimestamp,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/recovery/recovery-format";
import { formatDurationSeconds } from "@/app/(app)/recovery/[caseId]/case-format";
import {
  CaseSection,
  DefinitionRow,
} from "@/app/(app)/recovery/[caseId]/case-section";
import type {
  CaseCore,
  CaseOutcome,
} from "@/app/(app)/recovery/[caseId]/case-types";

interface CaseOutcomeCardProps {
  caseCore: CaseCore;
  outcome: CaseOutcome | null;
}

const TERMINAL_HEADLINE: Record<string, string> = {
  RECOVERED: "Recovered",
  FAILED: "Not recovered",
  STOPPED: "Stopped",
};

const TERMINAL_DESCRIPTION: Record<string, string> = {
  RECOVERED: "Revenue was verified and attributed to this case.",
  FAILED:
    "Recovery attempts were exhausted or a terminal unrecoverable condition was established.",
  STOPPED:
    "The workflow intentionally stopped without recovery, under policy or an operator decision.",
};

/**
 * Terminal-state module.
 *
 * All monetary and verification values come from the backend `outcome` payload.
 * Nothing is computed locally, and absent outcome fields degrade to a dash.
 */
export function CaseOutcomeCard({ caseCore, outcome }: CaseOutcomeCardProps) {
  const status = caseCore.status;
  const isRecovered = status === "RECOVERED";
  const headline = TERMINAL_HEADLINE[status] ?? humanizeEnumLabel(status);

  return (
    <CaseSection title="Outcome" headingId="case-outcome-heading">
      <div
        role="status"
        aria-live="polite"
        className={`rounded-md border p-4 ${
          isRecovered
            ? "border-emerald-300 bg-emerald-50"
            : "border-line bg-surface-hover"
        }`}
      >
        <p
          className={`text-sm font-semibold uppercase tracking-wide ${
            isRecovered ? "text-emerald-900" : "text-ink"
          }`}
        >
          {headline}
        </p>

        {isRecovered && outcome ? (
          <p className="mt-1 text-3xl font-semibold tabular-nums text-emerald-950">
            {safeMoney(outcome.recovered_amount_minor, caseCore.currency)}
          </p>
        ) : null}

        <p className="mt-2 text-sm text-ink">
          {TERMINAL_DESCRIPTION[status] ??
            "This case has reached a terminal state."}
        </p>

        {outcome ? (
          <p className="mt-1 text-sm text-ink">
            Verified via {humanizeEnumLabel(outcome.verification_source)}
          </p>
        ) : null}
      </div>

      {outcome ? (
        <dl className="mt-3">
          <DefinitionRow label="Outcome">
            {humanizeEnumLabel(outcome.outcome)}
          </DefinitionRow>
          <DefinitionRow label="Recovered amount">
            <span className="tabular-nums">
              {safeMoney(outcome.recovered_amount_minor, caseCore.currency)}
            </span>
          </DefinitionRow>
          <DefinitionRow label="Recovered at">
            {outcome.recovered_at
              ? formatExactTimestamp(outcome.recovered_at)
              : "—"}
          </DefinitionRow>
          <DefinitionRow label="Time to recovery">
            {formatDurationSeconds(outcome.time_to_recovery_seconds)}
          </DefinitionRow>
          <DefinitionRow label="Recovered payment ID">
            <span className="font-mono text-xs">
              {outcome.recovered_payment_id ?? "—"}
            </span>
          </DefinitionRow>
        </dl>
      ) : (
        <p className="mt-3 text-sm text-ink-muted">
          No outcome record is available for this case.
        </p>
      )}
    </CaseSection>
  );
}
