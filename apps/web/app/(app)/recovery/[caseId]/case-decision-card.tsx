import {
  formatRate,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/recovery/recovery-format";
import { CaseSection } from "@/app/(app)/recovery/[caseId]/case-section";
import { RadialGauge } from "@/components/gauges/radial-gauge";
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
 * Bar length per impact tier. The backend only reports a categorical tier
 * (HIGH/MEDIUM/LOW), not a numeric weight, so the bar communicates relative
 * strength honestly rather than implying false precision.
 */
const IMPACT_WIDTH: Record<string, number> = {
  HIGH: 100,
  MEDIUM: 62,
  LOW: 32,
};

const IMPACT_COLOR: Record<string, string> = {
  HIGH: "#4f46e5",
  MEDIUM: "#818cf8",
  LOW: "#c7d2fe",
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
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
            Recommended action
          </p>
          <p className="mt-1 font-display text-xl font-semibold text-neutral-900">
            {humanizeEnumLabel(analysis.selected_action)}
          </p>

          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <div>
              <p className="text-xs text-neutral-500">Expected recovery value</p>
              <p className="font-semibold tabular-nums text-neutral-900">
                {safeMoney(selectedCandidate?.expected_value_minor ?? null, currency)}
              </p>
            </div>
            <div>
              <p className="text-xs text-neutral-500">Expected recovered amount</p>
              <p className="font-semibold tabular-nums text-neutral-900">
                {safeMoney(
                  selectedCandidate?.expected_recovered_minor ?? null,
                  currency,
                )}
              </p>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 gap-3">
          <RadialGauge
            ratio={selectedCandidate?.success_probability ?? 0}
            color="#22d3ee"
            label="Estimated recovery probability"
            centerText={formatRate(selectedCandidate?.success_probability ?? null)}
          />
          <RadialGauge
            ratio={analysis.confidence}
            color="#818cf8"
            label="Confidence"
            centerText={formatRate(analysis.confidence)}
          />
        </div>
      </div>

      <p className="mt-3 text-[11px] text-neutral-500">
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
          <ul className="mt-2 space-y-2.5">
            {factors.map((factor) => {
              const width = IMPACT_WIDTH[factor.impact] ?? 20;
              const color = IMPACT_COLOR[factor.impact] ?? "#a3a3a3";
              return (
                <li key={`${factor.code}-${factor.source}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-neutral-800">
                    <span className="font-medium">{humanizeEnumLabel(factor.code)}</span>
                    <span className="flex items-center gap-2">
                      <span className="rounded border border-neutral-200 bg-neutral-50 px-1.5 py-0.5 text-[11px] font-medium">
                        {IMPACT_LABEL[factor.impact] ?? humanizeEnumLabel(factor.impact)}
                      </span>
                      <span className="text-xs text-neutral-500">
                        via {humanizeEnumLabel(factor.source)}
                      </span>
                    </span>
                  </div>
                  <div
                    className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-neutral-100"
                    role="img"
                    aria-label={`${humanizeEnumLabel(factor.code)}: ${
                      IMPACT_LABEL[factor.impact] ?? humanizeEnumLabel(factor.impact)
                    }`}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${width}%`, backgroundColor: color }}
                    />
                  </div>
                </li>
              );
            })}
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
