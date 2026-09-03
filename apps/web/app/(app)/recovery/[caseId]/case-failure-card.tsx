import { humanizeEnumLabel } from "@/app/(app)/recovery/recovery-format";
import {
  CaseSection,
  DefinitionRow,
} from "@/app/(app)/recovery/[caseId]/case-section";
import {
  isTransactionSource,
  type CaseCore,
  type CaseSource,
} from "@/app/(app)/recovery/[caseId]/case-types";

interface CaseFailureCardProps {
  caseCore: CaseCore;
  source: CaseSource;
}

/** Renders one provider evidence field, skipping blank values. */
function evidenceEntries(
  evidence: Record<string, unknown> | null | undefined,
): Array<[string, string]> {
  if (!evidence) {
    return [];
  }
  return Object.entries(evidence)
    .filter(
      ([, value]) =>
        value !== null && value !== undefined && String(value).trim() !== "",
    )
    .map(([key, value]) => [key, String(value)]);
}

/**
 * Failure and provider evidence.
 *
 * Raw evidence stays inside a collapsed disclosure so the card does not dump a
 * webhook payload by default, per FRONTEND_SPEC Screen 3 section B.
 */
export function CaseFailureCard({ caseCore, source }: CaseFailureCardProps) {
  const isTransaction = isTransactionSource(source);
  const evidence = evidenceEntries(
    isTransaction
      ? (source.failure_evidence as unknown as Record<string, unknown>)
      : source.failure_evidence,
  );

  return (
    <CaseSection title="Failure & evidence" headingId="case-failure-heading">
      <dl>
        <DefinitionRow label="Failure category">
          {humanizeEnumLabel(caseCore.failure_category)}
        </DefinitionRow>
        <DefinitionRow label="Provider status">
          {humanizeEnumLabel(source.provider_status)}
        </DefinitionRow>
        {isTransaction ? (
          <>
            <DefinitionRow label="Payment method">
              {source.payment_method
                ? humanizeEnumLabel(source.payment_method)
                : "—"}
            </DefinitionRow>
            <DefinitionRow label="Provider payment ID">
              <span className="font-mono text-xs">
                {source.provider_payment_id ?? "—"}
              </span>
            </DefinitionRow>
          </>
        ) : (
          <DefinitionRow label="Provider subscription ID">
            <span className="font-mono text-xs">
              {source.provider_subscription_id}
            </span>
          </DefinitionRow>
        )}
      </dl>

      {evidence.length > 0 ? (
        <details className="mt-3 rounded-md border border-neutral-200 bg-neutral-50 p-2">
          <summary className="cursor-pointer text-xs font-medium text-neutral-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500">
            Provider evidence ({evidence.length})
          </summary>
          <dl className="mt-2">
            {evidence.map(([key, value]) => (
              <DefinitionRow key={key} label={humanizeEnumLabel(key)}>
                <span className="font-mono text-xs break-all">{value}</span>
              </DefinitionRow>
            ))}
          </dl>
        </details>
      ) : (
        <p className="mt-3 text-xs text-neutral-500">
          No structured provider evidence was recorded for this case.
        </p>
      )}
    </CaseSection>
  );
}
