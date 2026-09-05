import {
  formatRate,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/recovery/recovery-format";
import { ErvWaterfall } from "@/app/(app)/simulator/erv-waterfall";
import { AdvisoryNotice } from "@/app/(app)/recovery/[caseId]/advisory-notice";
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
        <p className="text-sm text-ink-muted">
          No analysis has been published for this case yet.
        </p>
      </CaseSection>
    );
  }

  const explanation = analysis.structured_explanation;
  const factors = selectedCandidate?.factors ?? [];

  return (
    <CaseSection title="AI recovery decision" headingId="case-decision-heading">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        Recommended action
      </p>
      <p className="mt-1 text-lg font-semibold text-ink">
        {humanizeEnumLabel(analysis.selected_action)}
      </p>

      <AdvisoryNotice analysis={analysis} candidates={analysis.candidates} />

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

      {/* Binds the figures above to the action the CTA submits, WITHOUT
          repeating the action name as its own text node -- a second isolated
          copy of the same label makes every exact-text query on this card
          ambiguous. The name appears once, in the heading. */}
      <p className="mt-2 text-[11px] text-ink-muted">
        Probability is a model estimate, not a guarantee. Every figure above
        describes the recommended action named at the top of this card, which is
        the action the control below submits.
      </p>

      {/* The components are only present when they were persisted AND they
          reconcile with the stored total; the server withholds them otherwise
          rather than showing arithmetic that does not add up. */}
      {selectedCandidate?.erv_breakdown ? (
        <div className="mt-3">
          <ErvWaterfall
            currency={currency}
            expectedRecoveredMinor={
              selectedCandidate.erv_breakdown.expected_recovered_minor
            }
            actionCostMinor={selectedCandidate.erv_breakdown.action_cost_minor}
            fatiguePenaltyMinor={
              selectedCandidate.erv_breakdown.fatigue_penalty_minor
            }
            operationalRiskPenaltyMinor={
              selectedCandidate.erv_breakdown.operational_risk_penalty_minor
            }
            delayPenaltyMinor={
              selectedCandidate.erv_breakdown.delay_penalty_minor
            }
            expectedValueMinor={
              selectedCandidate.erv_breakdown.expected_value_minor
            }
          />
        </div>
      ) : null}

      <div className="mt-4">
        <h3 className="text-xs font-medium uppercase tracking-wide text-ink-muted">
          Why this action
        </h3>
        <p className="mt-1 text-sm text-ink">{explanation.summary}</p>

        {explanation.evidence.length > 0 ? (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink">
            {explanation.evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}

        {explanation.safety.length > 0 ? (
          <div className="mt-3">
            <h4 className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              Safety checks
            </h4>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink">
              {explanation.safety.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {factors.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-xs font-medium uppercase tracking-wide text-ink-muted">
            Top evidence factors
          </h3>
          <ul className="mt-1.5 space-y-1">
            {factors.map((factor) => (
              <li
                key={`${factor.code}-${factor.source}`}
                className="flex flex-wrap items-center gap-2 text-sm text-ink"
              >
                <span className="rounded border border-line bg-surface-hover px-1.5 py-0.5 text-[11px] font-medium">
                  {IMPACT_LABEL[factor.impact] ?? humanizeEnumLabel(factor.impact)}
                </span>
                <span>{humanizeEnumLabel(factor.code)}</span>
                <span className="text-xs text-ink-muted">
                  via {humanizeEnumLabel(factor.source)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="mt-4 border-t border-line pt-2 text-[11px] text-ink-muted">
        Model {analysis.model_version} · Features{" "}
        {analysis.feature_schema_version}
      </p>
    </CaseSection>
  );
}
