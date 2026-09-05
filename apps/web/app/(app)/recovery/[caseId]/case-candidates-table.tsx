import {
  formatRate,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/recovery/recovery-format";
import { AdvisoryChip } from "@/app/(app)/recovery/[caseId]/advisory-notice";
import { CaseSection } from "@/app/(app)/recovery/[caseId]/case-section";
import type { RecommendationCandidate } from "@/app/(app)/recovery/[caseId]/case-types";

interface CaseCandidatesTableProps {
  candidates: RecommendationCandidate[];
  currency: string;
  selectedAction: string | null;
}

const HEADER_CELL =
  "whitespace-nowrap px-3 py-2 text-xs font-semibold uppercase tracking-wide text-ink-muted";

/**
 * Candidate action comparison.
 *
 * Ranking, probabilities, monetary values and the policy verdict all come from
 * the backend analysis run. Blocked candidates stay visible with their reasons
 * rather than being hidden, per FRONTEND_SPEC Screen 3 section D.
 */
export function CaseCandidatesTable({
  candidates,
  currency,
  selectedAction,
}: CaseCandidatesTableProps) {
  if (candidates.length === 0) {
    return (
      <CaseSection
        title="Candidate action comparison"
        headingId="case-candidates-heading"
      >
        <p className="text-sm text-ink-muted">
          No candidate actions were produced for this case.
        </p>
      </CaseSection>
    );
  }

  const ordered = [...candidates].sort((a, b) => a.rank - b.rank);

  return (
    <CaseSection
      title="Candidate action comparison"
      headingId="case-candidates-heading"
    >
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[56rem] border-collapse text-sm">
          <caption className="sr-only">
            Candidate recovery actions ranked by the backend analysis run
          </caption>
          <thead>
            <tr className="border-b border-line text-left">
              <th scope="col" className={HEADER_CELL}>
                Rank
              </th>
              <th scope="col" className={HEADER_CELL}>
                Action
              </th>
              <th scope="col" className={`${HEADER_CELL} text-right`}>
                Success probability
              </th>
              <th scope="col" className={`${HEADER_CELL} text-right`}>
                Expected recovered
              </th>
              <th scope="col" className={`${HEADER_CELL} text-right`}>
                ERV
              </th>
              <th scope="col" className={HEADER_CELL}>
                Policy
              </th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((candidate) => {
              const isSelected = candidate.action_type === selectedAction;
              return (
                <tr
                  key={candidate.action_type}
                  className={`border-b border-line last:border-b-0 ${
                    isSelected ? "bg-surface-hover" : ""
                  }`}
                >
                  <td className="px-3 py-2.5 tabular-nums text-ink">
                    {candidate.rank}
                  </td>
                  <th scope="row" className="px-3 py-2.5 text-left font-normal">
                    <span className="font-medium text-ink">
                      {humanizeEnumLabel(candidate.action_type)}
                    </span>
                    {isSelected ? (
                      <span className="ml-2 rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] font-medium text-ink">
                        Selected
                      </span>
                    ) : null}
                    {candidate.execution_mode === "ADVISORY" ? (
                      <AdvisoryChip />
                    ) : null}
                    {candidate.execution_mode === "ADVISORY" &&
                    candidate.advisory_reason ? (
                      <span className="mt-1 block text-xs text-ink-muted">
                        {candidate.advisory_reason}
                      </span>
                    ) : null}
                  </th>
                  <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums text-ink">
                    {formatRate(candidate.success_probability)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums text-ink">
                    {safeMoney(candidate.expected_recovered_minor, currency)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums text-ink">
                    {safeMoney(candidate.expected_value_minor, currency)}
                  </td>
                  <td className="px-3 py-2.5">
                    {candidate.policy_eligible ? (
                      <span className="text-ink">
                        Eligible
                        {candidate.requires_approval
                          ? " · requires approval"
                          : ""}
                      </span>
                    ) : (
                      <span className="text-warning-ink">
                        <span className="font-medium">Blocked</span>
                        {candidate.policy_reasons.length > 0
                          ? `: ${candidate.policy_reasons
                              .map((reason) => humanizeEnumLabel(reason))
                              .join(", ")}`
                          : ""}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </CaseSection>
  );
}
