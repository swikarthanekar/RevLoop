import {
  ActionEffectivenessCard,
  FailureBreakdownCard,
  RecoveryTrendCard,
} from "@/app/(app)/dashboard/dashboard-charts";
import { DashboardKpis } from "@/app/(app)/dashboard/dashboard-kpis";
import { TopOpportunities } from "@/app/(app)/dashboard/top-opportunities";
import type { DashboardData } from "@/app/(app)/dashboard/dashboard-types";

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
    </div>
  );
}
