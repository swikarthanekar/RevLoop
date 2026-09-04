import type { DashboardSummary } from "@/app/(app)/dashboard/dashboard-types";
import {
  formatCount,
  formatDuration,
  formatRate,
  safeMoney,
} from "@/app/(app)/dashboard/dashboard-format";
import { AnimatedMoney } from "@/components/money/animated-money";

type KpiAccent = "risk" | "recovered" | "neutral";

const ACCENT_BAR: Record<KpiAccent, string> = {
  risk: "bg-amber-500",
  recovered: "bg-emerald-600",
  neutral: "bg-neutral-400",
};

interface KpiCardProps {
  label: string;
  context: string;
  accent?: KpiAccent;
  /** Static text value. Ignored when `animatedMoney` is supplied. */
  value?: string;
  /** When set, the value tweens between backend-provided snapshots instead of
   * rendering static text -- used for money figures a demo can watch move. */
  animatedMoney?: { amountMinor: number; currency: string };
}

function KpiCard({
  label,
  value,
  context,
  accent = "neutral",
  animatedMoney,
}: KpiCardProps) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-line bg-surface p-5">
      <span
        aria-hidden="true"
        className={`absolute inset-x-0 top-0 h-1 ${ACCENT_BAR[accent]}`}
      />
      <dt className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {label}
      </dt>
      <dd className="mt-2">
        {animatedMoney ? (
          <AnimatedMoney
            className="block text-3xl font-semibold tabular-nums tracking-tight text-ink"
            amountMinor={animatedMoney.amountMinor}
            currency={animatedMoney.currency}
          />
        ) : (
          <span className="block text-3xl font-semibold tabular-nums tracking-tight text-ink">
            {value}
          </span>
        )}
        <span className="mt-1 block text-sm text-ink-muted">{context}</span>
      </dd>
    </div>
  );
}

interface CompactStatProps {
  label: string;
  value: string;
}

function CompactStat({ label, value }: CompactStatProps) {
  return (
    <div className="flex flex-col gap-0.5 px-5 py-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </dt>
      <dd className="text-lg font-semibold tabular-nums text-ink">
        {value}
      </dd>
    </div>
  );
}

interface DashboardKpisProps {
  summary: DashboardSummary;
}

/**
 * Money-first KPI row. Every value is rendered straight from the dashboard
 * summary contract; nothing is derived or recomputed in the browser.
 */
export function DashboardKpis({ summary }: DashboardKpisProps) {
  const currency = summary.currency;

  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Revenue at Risk"
          animatedMoney={{ amountMinor: summary.revenue_at_risk_minor, currency }}
          context={`${formatCount(summary.active_cases)} active cases`}
          accent="risk"
        />
        <KpiCard
          label="Recovered Revenue"
          animatedMoney={{ amountMinor: summary.revenue_recovered_minor, currency }}
          context={`${formatCount(summary.recovered_cases)} recovered cases`}
          accent="recovered"
        />
        <KpiCard
          label="Recovery Rate"
          value={formatRate(summary.recovery_rate)}
          context="Share of at-risk revenue recovered"
        />
        <KpiCard
          label="Incremental vs Baseline"
          value={safeMoney(summary.incremental_recovered_minor, currency)}
          context={`Baseline ${safeMoney(summary.baseline_recovered_minor, currency)}`}
          accent="recovered"
        />
      </dl>

      <dl className="flex flex-wrap divide-y divide-line rounded-lg border border-line bg-surface sm:divide-x sm:divide-y-0">
        <CompactStat
          label="Active cases"
          value={formatCount(summary.active_cases)}
        />
        <CompactStat
          label="Recovered cases"
          value={formatCount(summary.recovered_cases)}
        />
        <CompactStat
          label="Avg. time to recover"
          value={formatDuration(summary.average_recovery_seconds)}
        />
      </dl>
    </div>
  );
}
