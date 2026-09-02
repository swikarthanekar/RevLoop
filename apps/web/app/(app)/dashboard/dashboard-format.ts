/**
 * Presentation-only formatting for the dashboard.
 *
 * Monetary values always go through the central `formatMoney` helper. Nothing in
 * this module derives a business value; it only makes backend-supplied values
 * readable.
 */

import { formatMoney } from "@/lib/money/format-money";

/**
 * Delegates to the central money formatter and degrades to a dash if the backend
 * ever sends a value the formatter rejects, so one bad field cannot break the page.
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

/** Renders a backend rate in the 0..1 range as a percentage string. */
export function formatRate(rate: number, fractionDigits = 1): string {
  if (!Number.isFinite(rate)) {
    return "—";
  }
  return `${(rate * 100).toFixed(fractionDigits)}%`;
}

/** Renders an integer count with locale grouping. */
export function formatCount(count: number): string {
  if (!Number.isFinite(count)) {
    return "—";
  }
  return new Intl.NumberFormat("en-IN").format(count);
}

/**
 * Renders `average_recovery_seconds`, which the contract allows to be null.
 * Null renders as an explicit dash rather than a fabricated duration.
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "—";
  }
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) {
    return `${total}s`;
  }
  const minutes = Math.floor(total / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) {
    return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
  }
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`;
}

/**
 * Formats an ISO `YYYY-MM-DD` trend date as a short axis label.
 * Parsed field-by-field so the output does not shift with the viewer timezone.
 */
export function formatTrendDate(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!match) {
    return isoDate;
  }
  const monthIndex = Number(match[2]) - 1;
  const month = MONTH_ABBREVIATIONS[monthIndex];
  if (!month) {
    return isoDate;
  }
  return `${Number(match[3])} ${month}`;
}

/** Formats an ISO timestamp as a short UTC date, e.g. "30 Aug 2026". */
export function formatIsoDate(isoTimestamp: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoTimestamp);
  if (!match) {
    return isoTimestamp;
  }
  const month = MONTH_ABBREVIATIONS[Number(match[2]) - 1];
  if (!month) {
    return isoTimestamp;
  }
  return `${Number(match[3])} ${month} ${match[1]}`;
}

/**
 * Turns a backend SCREAMING_SNAKE enum into sentence case for display.
 * The raw value is preserved for tooltips/labels by the caller when useful.
 */
export function humanizeEnumLabel(value: string): string {
  const cleaned = value.trim();
  if (!cleaned) {
    return "Unknown";
  }
  const words = cleaned.replace(/_/g, " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Turns the backend `source_label` into the demo provenance line required by the
 * spec. Unknown labels degrade to the raw value rather than claiming production.
 */
export function formatSourceLabel(sourceLabel: string): string {
  switch (sourceLabel) {
    case "SYNTHETIC_DEMO":
      return "Synthetic batch + Razorpay Test Mode";
    case "RAZORPAY_TEST":
      return "Razorpay Test Mode";
    default:
      return humanizeEnumLabel(sourceLabel);
  }
}
