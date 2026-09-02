interface InlineSkeletonProps {
  className?: string;
}

export function InlineSkeleton({ className = "h-4 w-24" }: InlineSkeletonProps) {
  return (
    <span
      className={`inline-block animate-pulse rounded bg-neutral-200 ${className}`}
      aria-hidden="true"
    />
  );
}

interface PageSectionSkeletonProps {
  title?: string;
}

export function PageSectionSkeleton({ title = "Loading section" }: PageSectionSkeletonProps) {
  return (
    <div className="space-y-3 rounded-lg border border-neutral-200 p-4" aria-busy="true">
      <span className="sr-only">{title}</span>
      <InlineSkeleton className="h-5 w-40" />
      <InlineSkeleton className="h-4 w-full" />
      <InlineSkeleton className="h-4 w-5/6" />
    </div>
  );
}

interface LoadingStateProps {
  label?: string;
}

export function LoadingState({ label = "Loading" }: LoadingStateProps) {
  return (
    <div className="flex items-center gap-2 text-sm text-neutral-600" aria-busy="true">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-700"
        aria-hidden="true"
      />
      <span>{label}</span>
    </div>
  );
}
