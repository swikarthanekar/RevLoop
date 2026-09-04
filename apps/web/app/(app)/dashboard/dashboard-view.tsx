import dynamic from "next/dynamic";

import {
  ActionEffectivenessCard,
  FailureBreakdownCard,
  RecoveryTrendCard,
} from "@/app/(app)/dashboard/dashboard-charts";
import { DashboardKpis } from "@/app/(app)/dashboard/dashboard-kpis";
import { RecoveryChannels } from "@/app/(app)/dashboard/recovery-channels";
import { TopOpportunities } from "@/app/(app)/dashboard/top-opportunities";
import type { DashboardData } from "@/app/(app)/dashboard/dashboard-types";
import { HeroSkeleton } from "@/components/hero-flow/hero-skeleton";

// The Three.js scene is client-only and non-trivial in size; it is loaded as
// its own chunk after the rest of the dashboard has already rendered.
const RevenueFlowHero = dynamic(
  () =>
    import("@/components/hero-flow/revenue-flow-hero").then(
      (mod) => mod.RevenueFlowHero,
    ),
  { ssr: false, loading: () => <HeroSkeleton /> },
);

interface DashboardViewProps {
  data: DashboardData;
}

/**
 * Ready-state dashboard body. Purely presentational: it renders values supplied
 * by the backend contract and performs no financial computation.
 */
export function DashboardView({ data }: DashboardViewProps) {
  const { summary, topOpportunities, topOpportunitiesUnavailable } = data;

  return (
    <div className="space-y-6">
      <RevenueFlowHero
        metrics={{
          revenueAtRiskMinor: summary.revenue_at_risk_minor,
          revenueRecoveredMinor: summary.revenue_recovered_minor,
          activeCases: summary.active_cases,
          recoveredCases: summary.recovered_cases,
          recoveryRate: summary.recovery_rate,
        }}
      />

      <DashboardKpis summary={summary} />

      <RecoveryTrendCard trend={summary.recovery_trend} currency={summary.currency} />

      {/* Anchor target for the Analytics navigation entry in the app shell. */}
      <div id="analytics" className="grid scroll-mt-20 grid-cols-1 gap-6 lg:grid-cols-2">
        <ActionEffectivenessCard
          rows={summary.action_effectiveness}
          currency={summary.currency}
        />
        <FailureBreakdownCard
          rows={summary.failure_breakdown}
          currency={summary.currency}
        />
      </div>

      <TopOpportunities
        items={topOpportunities}
        unavailable={topOpportunitiesUnavailable}
      />

      <RecoveryChannels />
    </div>
  );
}
