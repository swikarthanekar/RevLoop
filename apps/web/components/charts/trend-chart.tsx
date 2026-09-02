import {
  buildTicks,
  niceAxisMax,
  pickLabelIndices,
} from "@/components/charts/chart-utils";

export interface TrendPoint {
  /** Category label rendered on the x-axis. */
  label: string;
  values: number[];
}

export interface TrendSeries {
  id: string;
  label: string;
  /** Stroke colour. Series are also distinguished by stroke style. */
  color: string;
  /** Dashed strokes keep series distinguishable without relying on colour. */
  dashed?: boolean;
}

interface TrendChartProps {
  points: TrendPoint[];
  series: TrendSeries[];
  /** Formats axis ticks and tooltips. Supplied by the caller so money stays centralised. */
  formatValue: (value: number) => string;
  /** Accessible summary of what the chart shows. */
  ariaLabel: string;
}

const VIEWBOX_WIDTH = 720;
const VIEWBOX_HEIGHT = 280;
const PADDING = { top: 16, right: 16, bottom: 46, left: 96 };

const PLOT_WIDTH = VIEWBOX_WIDTH - PADDING.left - PADDING.right;
const PLOT_HEIGHT = VIEWBOX_HEIGHT - PADDING.top - PADDING.bottom;

export function TrendChart({
  points,
  series,
  formatValue,
  ariaLabel,
}: TrendChartProps) {
  const rawMax = points.reduce(
    (max, point) => Math.max(max, ...point.values.map((value) => value || 0)),
    0,
  );
  const axisMax = niceAxisMax(rawMax);
  const ticks = buildTicks(axisMax);
  const labelIndices = new Set(pickLabelIndices(points.length));

  const xFor = (index: number): number => {
    if (points.length <= 1) {
      return PADDING.left + PLOT_WIDTH / 2;
    }
    return PADDING.left + (PLOT_WIDTH / (points.length - 1)) * index;
  };

  const yFor = (value: number): number => {
    const ratio = axisMax > 0 ? Math.min(1, Math.max(0, value / axisMax)) : 0;
    return PADDING.top + PLOT_HEIGHT - ratio * PLOT_HEIGHT;
  };

  const baseline = PADDING.top + PLOT_HEIGHT;

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
        className="h-auto w-full"
        role="img"
        aria-label={ariaLabel}
      >
        {ticks.map((tick) => {
          const y = yFor(tick);
          return (
            <g key={`tick-${tick}`}>
              <line
                x1={PADDING.left}
                y1={y}
                x2={VIEWBOX_WIDTH - PADDING.right}
                y2={y}
                stroke="#e5e5e5"
                strokeWidth={1}
              />
              <text
                x={PADDING.left - 10}
                y={y + 4}
                textAnchor="end"
                fontSize={12}
                fill="#525252"
              >
                {formatValue(tick)}
              </text>
            </g>
          );
        })}

        <line
          x1={PADDING.left}
          y1={baseline}
          x2={VIEWBOX_WIDTH - PADDING.right}
          y2={baseline}
          stroke="#a3a3a3"
          strokeWidth={1}
        />

        {points.map((point, index) =>
          labelIndices.has(index) ? (
            <text
              key={`label-${point.label}`}
              x={xFor(index)}
              y={baseline + 22}
              textAnchor="middle"
              fontSize={12}
              fill="#525252"
            >
              {point.label}
            </text>
          ) : null,
        )}

        {series.map((line, seriesIndex) => {
          const coordinates = points.map((point, index) => ({
            x: xFor(index),
            y: yFor(point.values[seriesIndex] ?? 0),
          }));

          if (coordinates.length === 0) {
            return null;
          }

          const linePath = coordinates
            .map(
              (coordinate, index) =>
                `${index === 0 ? "M" : "L"} ${coordinate.x.toFixed(2)} ${coordinate.y.toFixed(2)}`,
            )
            .join(" ");

          const areaPath =
            coordinates.length > 1
              ? `${linePath} L ${coordinates[coordinates.length - 1].x.toFixed(2)} ${baseline} L ${coordinates[0].x.toFixed(2)} ${baseline} Z`
              : null;

          return (
            <g key={line.id}>
              {areaPath ? (
                <path d={areaPath} fill={line.color} fillOpacity={0.08} stroke="none" />
              ) : null}
              <path
                d={linePath}
                fill="none"
                stroke={line.color}
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeDasharray={line.dashed ? "7 5" : undefined}
              />
              {coordinates.map((coordinate, index) => (
                <circle
                  key={`${line.id}-${points[index].label}`}
                  cx={coordinate.x}
                  cy={coordinate.y}
                  r={coordinates.length > 24 ? 2 : 3.5}
                  fill="#ffffff"
                  stroke={line.color}
                  strokeWidth={2}
                >
                  <title>
                    {`${points[index].label} — ${line.label}: ${formatValue(
                      points[index].values[seriesIndex] ?? 0,
                    )}`}
                  </title>
                </circle>
              ))}
            </g>
          );
        })}
      </svg>

      <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
        {series.map((line) => (
          <span
            key={line.id}
            className="flex items-center gap-2 text-xs font-medium text-neutral-700"
          >
            <svg width={22} height={8} aria-hidden="true" className="shrink-0">
              <line
                x1={0}
                y1={4}
                x2={22}
                y2={4}
                stroke={line.color}
                strokeWidth={3}
                strokeLinecap="round"
                strokeDasharray={line.dashed ? "6 4" : undefined}
              />
            </svg>
            {line.label}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
