import { ratioOf, truncateLabel } from "@/components/charts/chart-utils";

export interface HorizontalBarDatum {
  id: string;
  /** Human-readable category label. */
  label: string;
  /** Numeric magnitude used only for bar geometry. */
  value: number;
  /** Pre-formatted display value, e.g. money from the central formatter. */
  valueLabel: string;
  /** Optional supporting detail rendered under the label and in the tooltip. */
  detail?: string;
}

interface HorizontalBarChartProps {
  data: HorizontalBarDatum[];
  /** Accessible summary of what the chart shows. */
  ariaLabel: string;
  barColor?: string;
}

/**
 * Horizontal bars sized against the largest value in the set. Every bar carries
 * a visible text label and value so the chart never relies on colour alone.
 */
export function HorizontalBarChart({
  data,
  ariaLabel,
  barColor = "#0369a1",
}: HorizontalBarChartProps) {
  const max = data.reduce((current, datum) => Math.max(current, datum.value || 0), 0);

  return (
    <ul className="m-0 flex list-none flex-col gap-4 p-0" aria-label={ariaLabel}>
      {data.map((datum) => {
        const widthPercent = ratioOf(datum.value, max) * 100;
        return (
          <li key={datum.id} className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-4">
              <span
                className="truncate text-sm font-medium text-neutral-800"
                title={datum.label}
              >
                {truncateLabel(datum.label, 40)}
              </span>
              <span className="shrink-0 text-sm font-semibold tabular-nums text-neutral-900">
                {datum.valueLabel}
              </span>
            </div>
            <div
              className="h-2.5 w-full overflow-hidden rounded-full bg-neutral-100"
              role="img"
              aria-label={`${datum.label}: ${datum.valueLabel}${
                datum.detail ? `, ${datum.detail}` : ""
              }`}
            >
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.max(widthPercent, datum.value > 0 ? 2 : 0)}%`,
                  backgroundColor: barColor,
                }}
              />
            </div>
            {datum.detail ? (
              <span className="text-xs text-neutral-600">{datum.detail}</span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
