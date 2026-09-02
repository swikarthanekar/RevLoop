import type { ReactNode } from "react";

interface DashboardSectionProps {
  title: string;
  description?: string;
  /** Rendered at the top-right of the section header, e.g. a count or note. */
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Card shell shared by every dashboard section, with a semantic h2 heading. */
export function DashboardSection({
  title,
  description,
  aside,
  children,
  className = "",
}: DashboardSectionProps) {
  return (
    <section
      className={`rounded-lg border border-neutral-200 bg-white p-5 ${className}`}
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-neutral-900">
            {title}
          </h2>
          {description ? (
            <p className="mt-0.5 text-sm text-neutral-600">{description}</p>
          ) : null}
        </div>
        {aside ? <div className="shrink-0">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}

interface SectionEmptyNoteProps {
  children: ReactNode;
}

/** Neutral in-section note used when a specific metric set has no rows. */
export function SectionEmptyNote({ children }: SectionEmptyNoteProps) {
  return (
    <p className="rounded-md border border-dashed border-neutral-300 bg-neutral-50 px-4 py-6 text-center text-sm text-neutral-600">
      {children}
    </p>
  );
}
