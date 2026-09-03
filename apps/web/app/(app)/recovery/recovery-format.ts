/**
 * Presentation-only formatting for the recovery list.
 *
 * Monetary values are delegated to the central `formatMoney` helper; nothing
 * here derives or recomputes a business value.
 */

import { formatMoney } from "@/lib/money/format-money";

const MONTH_ABBREVIATIONS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/**
 * Delegates to the central money formatter, degrading to a dash for values the
 * contract marks nullable or that the formatter rejects.
 */
export function safeMoney(
  amountMinor: number | string | null | undefined,
  currency: string,
): string {
  if (amountMinor === null || amountMinor === undefined) {
    return "—";
  }
  try {
    return formatMoney(amountMinor, currency);
  } catch {
    return "—";
  }
}

/** Renders a backend 0..1 probability/confidence as a percentage string. */
export function formatRate(
  rate: number | null | undefined,
  fractionDigits = 1,
): string {
  if (rate === null || rate === undefined || !Number.isFinite(rate)) {
    return "—";
  }
  return `${(rate * 100).toFixed(fractionDigits)}%`;
}

/** Turns a backend SCREAMING_SNAKE enum into sentence case for display. */
export function humanizeEnumLabel(value: string | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  const cleaned = value.trim();
  if (!cleaned) {
    return "—";
  }
  const words = cleaned.replace(/_/g, " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Compact relative age, e.g. "2d ago". `now` is injectable so the output is
 * deterministic under test.
 */
export function formatRelativeTime(
  isoTimestamp: string,
  now: number = Date.now(),
): string {
  const timestamp = Date.parse(isoTimestamp);
  if (Number.isNaN(timestamp)) {
    return "—";
  }
  const elapsedSeconds = Math.round((now - timestamp) / 1000);
  if (elapsedSeconds < 0) {
    return "just now";
  }
  if (elapsedSeconds < 60) {
    return "just now";
  }
  const minutes = Math.floor(elapsedSeconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 30) {
    return `${days}d ago`;
  }
  const months = Math.floor(days / 30);
  if (months < 12) {
    return `${months}mo ago`;
  }
  return `${Math.floor(months / 12)}y ago`;
}

/**
 * Exact UTC timestamp used as the tooltip beside the relative age, e.g.
 * "30 Aug 2026, 08:20 UTC".
 */
export function formatExactTimestamp(isoTimestamp: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(isoTimestamp);
  if (!match) {
    return isoTimestamp;
  }
  const month = MONTH_ABBREVIATIONS[Number(match[2]) - 1];
  if (!month) {
    return isoTimestamp;
  }
  return `${Number(match[3])} ${month} ${match[1]}, ${match[4]}:${match[5]} UTC`;
}

/** Formats a total row count with locale grouping. */
export function formatCount(count: number): string {
  if (!Number.isFinite(count)) {
    return "—";
  }
  return new Intl.NumberFormat("en-IN").format(count);
}
