import {
  formatExactTimestamp,
  formatRelativeTime,
} from "@/app/(app)/recovery/recovery-format";
import {
  formatActorLabel,
  formatEventName,
  formatSafeEvidence,
  getEventCategory,
} from "@/app/(app)/recovery/[caseId]/audit-timeline-format";
import type { TimelineEntry } from "@/app/(app)/recovery/[caseId]/case-types";

interface AuditTimelineEntryProps {
  entry: TimelineEntry;
}

/**
 * Decorative category marker.
 *
 * Purely visual and `aria-hidden`: the category is always also rendered as
 * text, so nothing depends on shape or colour alone.
 */
function CategoryMarker({ className }: { className: string }) {
  return (
    <span
      aria-hidden="true"
      className={`mt-1 flex h-3 w-3 shrink-0 rounded-full border-2 ${className}`}
    />
  );
}

/**
 * One audit entry.
 *
 * Renders only the five contract fields, and evidence only through the
 * allowlist in `audit-timeline-format.ts`. Nothing on this entry is derived
 * from unrelated case state.
 */
export function AuditTimelineEntry({ entry }: AuditTimelineEntryProps) {
  const category = getEventCategory(entry.event_type, entry.actor_type);
  const actorLabel = formatActorLabel(entry.actor_type);
  const evidence = formatSafeEvidence(entry.evidence);
  const isWarning = category.id === "warning";

  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      <CategoryMarker className={category.markerClass} />

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span
            className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium ${category.badgeClass}`}
          >
            {category.label}
          </span>
          <span className="font-mono text-xs font-semibold text-ink">
            {formatEventName(entry.event_type)}
          </span>
          {actorLabel ? (
            <span className="text-xs text-ink-muted">by {actorLabel}</span>
          ) : null}
          <time
            dateTime={entry.occurred_at}
            title={formatExactTimestamp(entry.occurred_at)}
            className="ml-auto text-xs tabular-nums text-ink-muted"
          >
            {formatRelativeTime(entry.occurred_at)}
          </time>
        </div>

        {/* `summary` is the contract's documented human-readable field. The
            domain model states it is an evidence summary, never model
            chain-of-thought. */}
        {entry.summary?.trim() ? (
          <p
            className={`mt-1 text-sm ${
              isWarning ? "text-rose-900" : "text-ink"
            }`}
          >
            {entry.summary}
          </p>
        ) : null}

        <p className="mt-0.5 text-xs text-ink-muted">
          <time dateTime={entry.occurred_at}>
            {formatExactTimestamp(entry.occurred_at)}
          </time>
        </p>

        {evidence.length > 0 ? (
          <details className="mt-2 rounded-md border border-line bg-surface-hover px-2 py-1.5">
            <summary className="cursor-pointer text-xs font-medium text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500">
              Details ({evidence.length})
            </summary>
            <dl className="mt-1.5">
              {evidence.map((item) => (
                <div
                  key={item.key}
                  className="flex items-baseline justify-between gap-4 border-b border-line py-1 last:border-b-0"
                >
                  <dt className="text-xs text-ink-muted">{item.label}</dt>
                  <dd
                    className={`text-right text-xs text-ink ${
                      item.mono ? "break-all font-mono" : ""
                    }`}
                  >
                    {item.value}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        ) : null}
      </div>
    </li>
  );
}
