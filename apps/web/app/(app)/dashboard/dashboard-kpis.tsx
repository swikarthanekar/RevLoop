import type { LucideIcon } from "lucide-react";
import { Clock3, Gauge, Layers, Sparkles, TrendingDown, TrendingUp } from "lucide-react";

import type { DashboardSummary } from "@/app/(app)/dashboard/dashboard-types";
import {
  formatCount,
  formatDuration,
  formatRate,
  safeMoney,
} from "@/app/(app)/dashboard/dashboard-format";
import { AnimatedMoney } from "@/components/money/animated-money";

type KpiTone = "risk" | "recovery" | "recovered" | "lift";

/** Color language shared with the dashboard's revenue-flow hero. */
const TONE: Record<
  KpiTone,
  { iconWrap: string; ring: string; text: string }
> = {
  risk: {
    iconWrap: "bg-gradient-to-br from-amber-400 to-orange-500",
    ring: "group-hover:ring-amber-200",
    text: "text-amber-700",
  },
  recovery: {
    iconWrap: "bg-gradient-to-br from-cyan-400 to-sky-500",
    ring: "group-hover:ring-cyan-200",
    text: "text-cyan-700",
  },
  recovered: {
    iconWrap: "bg-gradient-to-br from-emerald-400 to-teal-500",
    ring: "group-hover:ring-emerald-200",
    text: "text-emerald-700",
  },
  lift: {
    iconWrap: "bg-gradient-to-br from-indigo-400 to-violet-500",
    ring: "group-hover:ring-indigo-200",
    text: "text-indigo-700",
  },
};

interface KpiCardProps {
  label: string;
  context: string;
  tone: KpiTone;
  icon: LucideIcon;
  /** Static text value. Ignored when `animatedMoney` is supplied. */
  value?: string;
  /** When set, the value tweens between backend-provided snapshots instead of
   * rendering static text -- used for money figures a demo can watch move. */
  animatedMoney?: { amountMinor: number; currency: string };
}

function KpiCard({ label, value, context, tone, icon: Icon, animatedMoney }: KpiCardProps) {
  const palette = TONE[tone];
  return (
    <div
      className={`group glass-panel p-5 ring-1 ring-transparent transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glass-sm ${palette.ring}`}
    >
      <div className="flex items-start justify-between">
        <dt className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          {label}
        </dt>
        <span
          aria-hidden="true"
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white shadow-sm ${palette.iconWrap}`}
        >
          <Icon className="h-4 w-4" strokeWidth={2.25} />
        </span>
      </div>
      <dd className="mt-3">
        {animatedMoney ? (
          <AnimatedMoney
            className="block font-display text-3xl font-semibold tabular-nums tracking-tight text-neutral-900"
            amountMinor={animatedMoney.amountMinor}
            currency={animatedMoney.currency}
          />
        ) : (
          <span className="block font-display text-3xl font-semibold tabular-nums tracking-tight text-neutral-900">
            {value}
          </span>
        )}
        <span className="mt-1 block text-sm text-neutral-600">{context}</span>
      </dd>
    </div>
  );
}

interface CompactStatProps {
  label: string;
  value: string;
  icon: LucideIcon;
}

function CompactStat({ label, value, icon: Icon }: CompactStatProps) {
  return (
    <div className="flex flex-1 items-center gap-3 px-5 py-3">
      <Icon className="h-4 w-4 shrink-0 text-neutral-400" strokeWidth={2} aria-hidden="true" />
      <div className="flex flex-col gap-0.5">
        <dt className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          {label}
        </dt>
        <dd className="text-lg font-semibold tabular-nums text-neutral-900">
          {value}
        </dd>
      </div>
    </div>
  );
}

interface DashboardKpisProps {
  summary: DashboardSummary;
}

/**
 * Money-first KPI row. Every value is rendered straight from the dashboard
 * summary contract; nothing is derived or recomputed in the browser. Tones
 * reuse the same color language as the revenue-flow hero so a card and its
 * matching pipeline stage read as the same idea.
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
          tone="risk"
          icon={TrendingDown}
        />
        <KpiCard
          label="Recovered Revenue"
          animatedMoney={{ amountMinor: summary.revenue_recovered_minor, currency }}
          context={`${formatCount(summary.recovered_cases)} recovered cases`}
          tone="recovered"
          icon={TrendingUp}
        />
        <KpiCard
          label="Recovery Rate"
          value={formatRate(summary.recovery_rate)}
          context="Share of at-risk revenue recovered"
          tone="recovery"
          icon={Gauge}
        />
        <KpiCard
          label="Incremental vs Baseline"
          value={safeMoney(summary.incremental_recovered_minor, currency)}
          context={`Baseline ${safeMoney(summary.baseline_recovered_minor, currency)}`}
          tone="lift"
          icon={Sparkles}
        />
      </dl>

      <dl className="flex flex-wrap divide-y divide-neutral-200 rounded-xl border border-neutral-200 bg-white sm:divide-x sm:divide-y-0">
        <CompactStat
          label="Active cases"
          value={formatCount(summary.active_cases)}
          icon={Layers}
        />
        <CompactStat
          label="Recovered cases"
          value={formatCount(summary.recovered_cases)}
          icon={TrendingUp}
        />
        <CompactStat
          label="Avg. time to recover"
          value={formatDuration(summary.average_recovery_seconds)}
          icon={Clock3}
        />
      </dl>
    </div>
  );
}
