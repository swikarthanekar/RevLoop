import type { ReactNode } from "react";

interface CaseSectionProps {
  title: string;
  description?: string;
  headingId?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

/**
 * Shared card shell, matching the border/spacing language used by the dashboard
 * and recovery list so the detail view reads as the same product.
 */
export function CaseSection({
  title,
  description,
  headingId,
  actions,
  children,
  className = "",
}: CaseSectionProps) {
  return (
    <section
      aria-labelledby={headingId}
      className={`rounded-lg border border-line bg-surface p-4 ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2
            id={headingId}
            className="text-sm font-semibold uppercase tracking-wide text-ink-muted"
          >
            {title}
          </h2>
          {description ? (
            <p className="mt-1 text-sm text-ink-muted">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

interface DefinitionRowProps {
  label: string;
  children: ReactNode;
}

/** Compact label/value pair used across the evidence and decision cards. */
export function DefinitionRow({ label, children }: DefinitionRowProps) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-1.5 last:border-b-0">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="text-right text-sm text-ink">{children}</dd>
    </div>
  );
}
