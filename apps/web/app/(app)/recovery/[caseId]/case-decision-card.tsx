import {
  formatRate,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/recovery/recovery-format";
import {
  CaseSection,
  DefinitionRow,
} from "@/app/(app)/recovery/[caseId]/case-section";
import type {
  CaseAnalysis,
  RecommendationCandidate,
} from "@/app/(app)/recovery/[caseId]/case-types";

interface CaseDecisionCardProps {
  analysis: CaseAnalysis | null;
  currency: string;
  /** The candidate matching `analysis.selected_action`, when present. */
  selectedCandidate: RecommendationCandidate | null;
}

const IMPACT_LABEL: Record<string, string> = {
  HIGH: "High impact",
  MEDIUM: "Medium impact",
  LOW: "Low impact",
};

/**
 * AI recovery decision.
 *
 * Every number here is read verbatim from the analysis payload. The frontend
 * does not compute probability, expected recovery value or confidence.
 */
export function CaseDecisionCard({
  analysis,
  currency,
  selectedCandidate,
}: CaseDecisionCardProps) {
  if (!analysis) {
    return (
      <CaseSection
        title="AI recovery decision"
        headingId="case-decision-heading"
      >
        <p className="text-sm text-neutral-600">
          No analysis has been published for this case yet.
        </p>
      </CaseSection>
    );
  }

  const explanation = analysis.structured_explanation;
  const factors = selectedCandidate?.factors ?? [];

  return (
    <CaseSection title="AI recovery decision" headingId="case-decision-heading">
      <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
        Recommended action
      </p>
      <p className="mt-1 text-lg font-semibold text-neutral-900">
        {humanizeEnumLabel(analysis.selected_action)}
      </p>

      <dl className="mt-3">
        <DefinitionRow label="Estimated recovery probability">
          <span className="tabular-nums">
            {formatRate(selectedCandidate?.success_probability ?? null)}
          </span>
        </DefinitionRow>
        <DefinitionRow label="Expected recovery value">
          <span className="tabular-nums">
            {safeMoney(selectedCandidate?.expected_value_minor ?? null, currency)}
          </span>
        </DefinitionRow>
        <DefinitionRow label="Expected recovered amount">
          <span className="tabular-nums">
            {safeMoney(
              selectedCandidate?.expected_recovered_minor ?? null,
              currency,
            )}
          </span>
        </DefinitionRow>
        <DefinitionRow label="Confidence">
          <span className="tabular-nums">{formatRate(analysis.confidence)}</span>
        </DefinitionRow>
      </dl>

      <p className="mt-2 text-[11px] text-neutral-500">
        Probability is a model estimate, not a guarantee.
      </p>

      <div className="mt-4">
        <h3 className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          Why this action
        </h3>
        <p className="mt-1 text-sm text-neutral-800">{explanation.summary}</p>

        {explanation.evidence.length > 0 ? (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-neutral-700">
            {explanation.evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}

        {explanation.safety.length > 0 ? (
          <div className="mt-3">
            <h4 className="text-xs font-medium uppercase tracking-wide text-neutral-500">
              Safety checks
            </h4>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-neutral-700">
              {explanation.safety.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {factors.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-xs font-medium uppercase tracking-wide text-neutral-500">
            Top evidence factors
          </h3>
          <ul className="mt-1.5 space-y-1">
            {factors.map((factor) => (
              <li
                key={`${factor.code}-${factor.source}`}
                className="flex flex-wrap items-center gap-2 text-sm text-neutral-800"
              >
                <span className="rounded border border-neutral-200 bg-neutral-50 px-1.5 py-0.5 text-[11px] font-medium">
                  {IMPACT_LABEL[factor.impact] ?? humanizeEnumLabel(factor.impact)}
                </span>
                <span>{humanizeEnumLabel(factor.code)}</span>
                <span className="text-xs text-neutral-500">
                  via {humanizeEnumLabel(factor.source)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="mt-4 border-t border-neutral-100 pt-2 text-[11px] text-neutral-500">
        Model {analysis.model_version} · Features{" "}
        {analysis.feature_schema_version}
      </p>
    </CaseSection>
  );
}
