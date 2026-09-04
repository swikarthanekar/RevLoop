const SIZE = 76;
const STROKE = 7;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

interface RadialGaugeProps {
  /** 0..1. Values outside that range are clamped, never fabricated. */
  ratio: number;
  color: string;
  label: string;
  /** Pre-formatted text rendered at the gauge's center, e.g. "82.0%". */
  centerText: string;
  /** Set false when a caller already renders `label` next to the gauge. */
  showLabel?: boolean;
}

/**
 * Small circular progress ring for a 0..1 backend value. Purely a visual
 * restatement of `centerText` -- the number itself always comes from the
 * caller, this component never computes a ratio of its own. `label` is
 * always used for the accessible name, even when its visible caption
 * (`showLabel`) is suppressed because a caller renders it elsewhere.
 */
export function RadialGauge({
  ratio,
  color,
  label,
  centerText,
  showLabel = true,
}: RadialGaugeProps) {
  const clamped = Number.isFinite(ratio) ? Math.min(1, Math.max(0, ratio)) : 0;
  const offset = CIRCUMFERENCE * (1 - clamped);

  return (
    <div className="flex w-[76px] flex-col items-center gap-1.5">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`${label}: ${centerText}`}>
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={STROKE}
        />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="middle"
          textAnchor="middle"
          className="fill-neutral-900 font-display text-[15px] font-semibold tabular-nums"
        >
          {centerText}
        </text>
      </svg>
      {showLabel ? (
        <p className="text-center text-[11px] font-medium uppercase tracking-wide text-neutral-500">
          {label}
        </p>
      ) : null}
    </div>
  );
}
