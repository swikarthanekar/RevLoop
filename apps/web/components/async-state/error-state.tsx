import { mapApiError } from "@/lib/api/error-mapper";
import { ApiError } from "@/lib/api/api-error";

interface ErrorStateProps {
  error: ApiError | Error;
  onRetry?: () => void;
  title?: string;
}

export function ErrorState({ error, onRetry, title }: ErrorStateProps) {
  const presentation =
    error instanceof ApiError ? mapApiError(error) : {
      title: title ?? "Something went wrong",
      message: error.message,
      guidance: "Try again or refresh the page.",
    };

  return (
    <div
      className="rounded-lg border border-danger-border bg-danger-surface p-4 text-sm text-danger-ink"
      role="alert"
      aria-live="polite"
    >
      <p className="font-medium">{presentation.title}</p>
      <p className="mt-1">{presentation.message}</p>
      <p className="mt-2 text-danger-ink opacity-90">{presentation.guidance}</p>
      {error instanceof ApiError && error.requestId ? (
        <p className="mt-2 text-xs text-danger-ink opacity-80">Reference: {error.requestId}</p>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-danger-border bg-surface px-3 py-1.5 text-xs font-medium text-danger-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  description: string;
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-surface-hover p-6 text-sm text-ink">
      <p className="font-medium text-ink">{title}</p>
      <p className="mt-1">{description}</p>
    </div>
  );
}
