import {
  HorizontalBarChart,
  type HorizontalBarDatum,
} from "@/components/charts/horizontal-bar-chart";
import { TrendChart, type TrendPoint } from "@/components/charts/trend-chart";
import {
  DashboardSection,
  SectionEmptyNote,
} from "@/app/(app)/dashboard/dashboard-section";
import {
  formatCount,
  formatRate,
  formatTrendDate,
  humanizeEnumLabel,
  safeMoney,
} from "@/app/(app)/dashboard/dashboard-format";
import type {
  ActionEffectivenessRow,
  FailureBreakdownRow,
  RecoveryTrendPoint,
} from "@/app/(app)/dashboard/dashboard-types";

const AT_RISK_COLOR = "#b45309";
const RECOVERED_COLOR = "#047857";

interface RecoveryTrendCardProps {
  trend: RecoveryTrendPoint[];
  currency: string;
}

/**
 * Recovery trend over time. A two-series line/area chart is the simplest form
 * that shows at-risk and recovered amounts moving against each other.
 */
export function RecoveryTrendCard({ trend, currency }: RecoveryTrendCardProps) {
  const points: TrendPoint[] = trend.map((point) => ({
    label: formatTrendDate(point.date),
    values: [point.at_risk_minor, point.recovered_minor],
  }));

  return (
    <DashboardSection
      title="Recovery trend"
      description="At-risk versus recovered revenue over the reported period."
    >
      {points.length === 0 ? (
        <SectionEmptyNote>
          No trend data has been reported for this period yet.
        </SectionEmptyNote>
      ) : (
        <TrendChart
          points={points}
          series={[
            { id: "at_risk", label: "At risk", color: AT_RISK_COLOR },
            {
              id: "recovered",
              label: "Recovered",
              color: RECOVERED_COLOR,
              dashed: true,
            },
          ]}
          formatValue={(value) => safeMoney(Math.round(value), currency)}
          ariaLabel={`Recovery trend across ${points.length} reporting days, comparing at-risk and recovered revenue`}
        />
      )}
    </DashboardSection>
  );
}

interface ActionEffectivenessCardProps {
  rows: ActionEffectivenessRow[];
  currency: string;
}

/**
 * Action effectiveness. Horizontal bars ranked by recovery rate keep long action
 * names readable, which a vertical bar chart cannot do.
 */
export function ActionEffectivenessCard({
  rows,
  currency,
}: ActionEffectivenessCardProps) {
  const data: HorizontalBarDatum[] = rows.map((row) => ({
    id: row.action_type,
    label: humanizeEnumLabel(row.action_type),
    value: row.recovery_rate,
    valueLabel: formatRate(row.recovery_rate),
    detail: `${formatCount(row.recovered)} of ${formatCount(
      row.attempted,
    )} attempts · ${safeMoney(row.recovered_minor, currency)} recovered`,
  }));

  return (
    <DashboardSection
      title="Action effectiveness"
      description="Recovery rate by action type, with attempts and recovered amount."
    >
      {data.length === 0 ? (
        <SectionEmptyNote>
          No recovery actions have completed yet.
        </SectionEmptyNote>
      ) : (
        <HorizontalBarChart
          data={data}
          barColor={RECOVERED_COLOR}
          ariaLabel="Recovery rate by action type"
        />
      )}
    </DashboardSection>
  );
}

interface FailureBreakdownCardProps {
  rows: FailureBreakdownRow[];
  currency: string;
}

/**
 * Failure breakdown by amount at risk. Bars are preferred over a donut because
 * the categories must be compared by monetary size and labelled in full.
 */
export function FailureBreakdownCard({
  rows,
  currency,
}: FailureBreakdownCardProps) {
  const data: HorizontalBarDatum[] = rows.map((row) => ({
    id: row.failure_category,
    label: humanizeEnumLabel(row.failure_category),
    value: row.amount_minor,
    valueLabel: safeMoney(row.amount_minor, currency),
    detail: `${formatCount(row.cases)} cases`,
  }));

  return (
    <DashboardSection
      title="Failure breakdown"
      description="Amount at risk grouped by normalized failure category."
    >
      {data.length === 0 ? (
        <SectionEmptyNote>
          No failure categories have been reported yet.
        </SectionEmptyNote>
      ) : (
        <HorizontalBarChart
          data={data}
          barColor={AT_RISK_COLOR}
          ariaLabel="Amount at risk by failure category"
        />
      )}
    </DashboardSection>
  );
}
