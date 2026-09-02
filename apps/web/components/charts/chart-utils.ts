/**
 * Geometry helpers shared by the dashboard charts.
 *
 * These helpers are deliberately presentation-only: they scale numbers into SVG
 * coordinates and never derive business meaning. Monetary values arrive already
 * formatted from the caller so currency logic stays in the central formatter.
 */

/** Rounds an axis maximum up to a readable 1/2/5 x 10^n boundary. */
export function niceAxisMax(rawMax: number): number {
  if (!Number.isFinite(rawMax) || rawMax <= 0) {
    return 1;
  }
  const magnitude = 10 ** Math.floor(Math.log10(rawMax));
  const normalized = rawMax / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

/** Evenly spaced tick values from 0 to max inclusive. */
export function buildTicks(max: number, tickCount = 4): number[] {
  const safeMax = max > 0 ? max : 1;
  const safeCount = Math.max(1, tickCount);
  return Array.from(
    { length: safeCount + 1 },
    (_value, index) => (safeMax / safeCount) * index,
  );
}

/**
 * Picks which category labels to render so a dense x-axis stays legible.
 * Always keeps the first and last entry.
 */
export function pickLabelIndices(total: number, maxLabels = 6): number[] {
  if (total <= 0) {
    return [];
  }
  if (total <= maxLabels) {
    return Array.from({ length: total }, (_value, index) => index);
  }
  const stride = (total - 1) / (maxLabels - 1);
  const indices = new Set<number>();
  for (let step = 0; step < maxLabels; step += 1) {
    indices.add(Math.round(step * stride));
  }
  indices.add(total - 1);
  return [...indices].sort((left, right) => left - right);
}

/** Ratio of value to max, clamped to 0..1 and safe when max is zero. */
export function ratioOf(value: number, max: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(max) || max <= 0) {
    return 0;
  }
  return Math.min(1, Math.max(0, value / max));
}

/** Shortens a long category label without hiding the distinguishing prefix. */
export function truncateLabel(label: string, maxLength = 28): string {
  if (label.length <= maxLength) {
    return label;
  }
  return `${label.slice(0, maxLength - 1).trimEnd()}…`;
}
