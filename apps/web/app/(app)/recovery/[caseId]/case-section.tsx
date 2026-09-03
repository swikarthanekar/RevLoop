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
      className={`rounded-lg border border-neutral-200 bg-white p-4 ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2
            id={headingId}
            className="text-sm font-semibold uppercase tracking-wide text-neutral-500"
          >
            {title}
          </h2>
          {description ? (
            <p className="mt-1 text-sm text-neutral-600">{description}</p>
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
    <div className="flex items-baseline justify-between gap-4 border-b border-neutral-100 py-1.5 last:border-b-0">
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="text-right text-sm text-neutral-900">{children}</dd>
    </div>
  );
}
