import { humanizeEnumLabel } from "@/app/(app)/recovery/recovery-format";
import type {
  CaseAnalysis,
  RecommendationCandidate,
} from "@/app/(app)/recovery/[caseId]/case-types";

interface AdvisoryNoticeProps {
  analysis: CaseAnalysis;
  candidates: RecommendationCandidate[];
}

/**
 * Shown when the model's top-ranked action is one RevLoop does not execute.
 *
 * This is deliberately a sentence rather than a badge. A bare "ADVISORY" tag
 * reads as unfinished work; stating the reason turns the same fact into an
 * explanation of a boundary the product drew on purpose — RevLoop holds no
 * mandate, so it does not invent an autonomous debit, and executes the best
 * action it genuinely can instead.
 *
 * Every string here comes from the server (`top_ranked_action`,
 * `advisory_reason`). The capability rule lives in one place, in the backend's
 * `app/domain/capabilities.py`; this component never decides what is executable.
 */
export function AdvisoryNotice({ analysis, candidates }: AdvisoryNoticeProps) {
  const topRanked = analysis.top_ranked_action;
  if (!topRanked || topRanked === analysis.selected_action) {
    return null;
  }

  const topCandidate =
    candidates.find((candidate) => candidate.action_type === topRanked) ?? null;

  // Only explain a capability boundary here. When the top-ranked action was
  // skipped because policy blocked it, the policy panel already says so and
  // repeating it as a capability limit would be wrong.
  if (topCandidate?.execution_mode !== "ADVISORY") {
    return null;
  }

  return (
    <div className="mt-3 rounded-md border border-info-border bg-info-surface p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-info-ink">
        Why not {humanizeEnumLabel(topRanked).toLowerCase()}?
      </p>
      <p className="mt-1.5 text-sm text-info-ink">
        The model ranks{" "}
        <span className="font-medium">{humanizeEnumLabel(topRanked)}</span>{" "}
        highest for this case.{" "}
        {topCandidate.advisory_reason ??
          "RevLoop does not execute this action type itself."}
      </p>
      {/* Deliberately not an isolated <span> holding just the action label:
          that would be a second element whose exact text equals the heading's,
          making exact-text queries on this card ambiguous. */}
      <p className="mt-1.5 text-sm text-info-ink">
        <span className="font-medium">
          Executing {humanizeEnumLabel(analysis.selected_action)} instead
        </span>{" "}
        — the highest-ranked action RevLoop can carry out.
      </p>
    </div>
  );
}

/** Compact marker for an advisory row in the candidate table. */
export function AdvisoryChip() {
  return (
    <span className="ml-2 whitespace-nowrap rounded border border-info-border bg-info-surface px-1.5 py-0.5 text-[11px] font-medium text-info-ink">
      Advisory
    </span>
  );
}
