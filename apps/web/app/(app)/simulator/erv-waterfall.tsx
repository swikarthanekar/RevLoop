import { formatMoney } from "@/lib/money/format-money";

interface ErvWaterfallProps {
  currency: string;
  expectedRecoveredMinor: number;
  actionCostMinor: number;
  fatiguePenaltyMinor: number;
  operationalRiskPenaltyMinor: number;
  delayPenaltyMinor: number;
  expectedValueMinor: number;
}

function money(minor: number, currency: string): string {
  try {
    return formatMoney(minor, currency);
  } catch {
    return "—";
  }
}

/**
 * The arithmetic behind one candidate's expected value.
 *
 * The engine already computed these five components; only the first and the
 * net total were ever shown, which left "expected recovery value" looking like
 * an unexplained number. Showing the subtraction turns it into something a
 * reader can check.
 *
 * Every figure is supplied by the server. Nothing here is derived — in
 * particular the total is the server's `expected_value_minor`, not a sum
 * computed in the browser, so a discrepancy would be visible rather than
 * silently papered over by the renderer agreeing with itself.
 */
export function ErvWaterfall({
  currency,
  expectedRecoveredMinor,
  actionCostMinor,
  fatiguePenaltyMinor,
  operationalRiskPenaltyMinor,
  delayPenaltyMinor,
  expectedValueMinor,
}: ErvWaterfallProps) {
  const deductions = [
    { label: "Action cost", value: actionCostMinor },
    { label: "Contact fatigue", value: fatiguePenaltyMinor },
    { label: "Operational risk", value: operationalRiskPenaltyMinor },
    { label: "Delay penalty", value: delayPenaltyMinor },
  ].filter((row) => row.value > 0);

  const scale = Math.max(expectedRecoveredMinor, 1);

  return (
    <div className="rounded-md border border-line bg-surface-hover p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        How expected value is derived
      </p>

      <dl className="mt-2.5 space-y-1.5">
        <div className="flex items-baseline justify-between gap-4">
          <dt className="text-sm text-ink">Expected recovery</dt>
          <dd className="tabular-nums text-sm font-medium text-ink">
            {money(expectedRecoveredMinor, currency)}
          </dd>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-surface-active"
          aria-hidden="true"
        >
          <div className="h-full rounded-full bg-success-border" style={{ width: "100%" }} />
        </div>

        {deductions.length === 0 ? (
          <p className="pt-1 text-xs text-ink-muted">
            No deductions apply to this action.
          </p>
        ) : (
          deductions.map((row) => (
            <div key={row.label} className="pt-1">
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-sm text-ink-muted">− {row.label}</dt>
                <dd className="tabular-nums text-sm text-danger-ink">
                  −{money(row.value, currency)}
                </dd>
              </div>
              <div
                className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-active"
                aria-hidden="true"
              >
                <div
                  className="h-full rounded-full bg-danger-border"
                  style={{
                    width: `${Math.max(1, Math.min(100, (row.value / scale) * 100))}%`,
                  }}
                />
              </div>
            </div>
          ))
        )}

        <div className="flex items-baseline justify-between gap-4 border-t border-line pt-2">
          <dt className="text-sm font-medium text-ink">Expected value</dt>
          <dd className="tabular-nums text-base font-semibold text-ink">
            {money(expectedValueMinor, currency)}
          </dd>
        </div>
      </dl>

      <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">
        Computed server-side in integer minor units with explicit rounding. The
        browser never recalculates these figures.
      </p>
    </div>
  );
}
