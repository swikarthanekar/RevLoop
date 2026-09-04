/**
 * Presentation-only formatting for the Compliance Guardrails page. Monetary
 * values always go through the central `formatMoney` helper.
 */

/**
 * Turns a backend SCREAMING_SNAKE enum into sentence case for display.
 * Local copy matching the convention already used by the dashboard and
 * recovery feature folders -- each feature owns its own formatter rather
 * than importing across feature boundaries.
 */
export function humanizeEnumLabel(value: string): string {
  const cleaned = value.trim();
  if (!cleaned) {
    return "Unknown";
  }
  const words = cleaned.replace(/_/g, " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
