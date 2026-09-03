/**
 * Case-detail specific formatting.
 *
 * Shared formatters (`safeMoney`, `formatRate`, `humanizeEnumLabel`,
 * timestamps) are imported from the sibling recovery module rather than
 * duplicated, since the case detail route lives under the same feature folder.
 */

/**
 * Renders a backend-supplied duration in seconds as a compact human string.
 * Used for `outcome.time_to_recovery_seconds`, which the contract marks nullable.
 */
export function formatDurationSeconds(
  seconds: number | null | undefined,
): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "—";
  }
  if (seconds < 0) {
    return "—";
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    const remainingMinutes = minutes % 60;
    return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
  }
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours ? `${days}d ${remainingHours}h` : `${days}d`;
}
