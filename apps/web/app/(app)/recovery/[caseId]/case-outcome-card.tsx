"use client";

import { motion, useReducedMotion } from "framer-motion";

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

const BURST_ANGLES_DEG = [0, 45, 90, 135, 180, 225, 270, 315];

/** One-time radiating burst behind the recovered amount. Decorative only. */
function RecoveredBurst() {
  return (
    <span
      className="pointer-events-none absolute inset-0 flex items-center justify-center"
      aria-hidden="true"
    >
      {BURST_ANGLES_DEG.map((angle) => (
        <motion.span
          key={angle}
          className="absolute h-1.5 w-1.5 rounded-full bg-emerald-400"
          initial={{ x: 0, y: 0, opacity: 0, scale: 0.5 }}
          animate={{
            x: Math.cos((angle * Math.PI) / 180) * 70,
            y: Math.sin((angle * Math.PI) / 180) * 70,
            opacity: [0, 1, 0],
            scale: [0.5, 1, 0.4],
          }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
      ))}
    </span>
  );
}

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
  const reducedMotion = useReducedMotion();

  return (
    <CaseSection title="Outcome" headingId="case-outcome-heading">
      <div
        role="status"
        aria-live="polite"
        className={`relative overflow-hidden rounded-md border p-4 ${
          isRecovered
            ? "border-emerald-300 bg-emerald-50"
            : "border-neutral-300 bg-neutral-50"
        }`}
      >
        {isRecovered && !reducedMotion ? <RecoveredBurst /> : null}

        <p
          className={`relative text-sm font-semibold uppercase tracking-wide ${
            isRecovered ? "text-emerald-900" : "text-neutral-800"
          }`}
        >
          {headline}
        </p>

        {isRecovered && outcome ? (
          <motion.p
            initial={reducedMotion ? false : { opacity: 0, scale: 0.85, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 20 }}
            className="relative mt-1 font-display text-3xl font-semibold tabular-nums text-emerald-950"
          >
            {safeMoney(outcome.recovered_amount_minor, caseCore.currency)}
          </motion.p>
        ) : null}

        <p className="mt-2 text-sm text-neutral-700">
          {TERMINAL_DESCRIPTION[status] ??
            "This case has reached a terminal state."}
        </p>

        {outcome ? (
          <p className="mt-1 text-sm text-neutral-700">
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
        <p className="mt-3 text-sm text-neutral-600">
          No outcome record is available for this case.
        </p>
      )}
    </CaseSection>
  );
}
