import { formatRate, humanizeEnumLabel } from "@/app/(app)/recovery/recovery-format";

interface SegmentBadgeProps {
  segment: string;
}

/**
 * Customer segment badge. High-value customers get extra emphasis, but the
 * segment name is always spelled out so the signal is never colour-only.
 */
export function SegmentBadge({ segment }: SegmentBadgeProps) {
  const isHighValue = segment.trim().toUpperCase() === "HIGH_VALUE";
  const tone = isHighValue
    ? "border-violet-200 bg-violet-50 text-violet-800"
    : "border-line bg-surface-hover text-ink";

  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium ${tone}`}
    >
      {humanizeEnumLabel(segment)}
    </span>
  );
}

interface ConfidenceMeterProps {
  /** Backend confidence in the 0..1 range, or null when not yet scored. */
  confidence: number | null;
}

/**
 * Confidence shown as a labelled meter. The numeric value is always rendered as
 * text, so the bar is a secondary cue rather than the only one.
 */
export function ConfidenceMeter({ confidence }: ConfidenceMeterProps) {
  if (confidence === null || !Number.isFinite(confidence)) {
    return <span className="text-ink-muted">—</span>;
  }

  const percent = Math.min(100, Math.max(0, confidence * 100));

  return (
    <span className="flex items-center gap-2">
      <span
        className="h-1.5 w-12 shrink-0 overflow-hidden rounded-full bg-line"
        aria-hidden="true"
      >
        <span
          className="block h-full rounded-full bg-neutral-600"
          style={{ width: `${percent}%` }}
        />
      </span>
      <span className="tabular-nums text-ink">
        {formatRate(confidence, 0)}
      </span>
    </span>
  );
}
