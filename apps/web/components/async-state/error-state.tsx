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
      className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"
      role="alert"
      aria-live="polite"
    >
      <p className="font-medium">{presentation.title}</p>
      <p className="mt-1">{presentation.message}</p>
      <p className="mt-2 text-rose-800">{presentation.guidance}</p>
      {error instanceof ApiError && error.requestId ? (
        <p className="mt-2 text-xs text-rose-700">Reference: {error.requestId}</p>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-rose-300 bg-surface px-3 py-1.5 text-xs font-medium text-rose-900 hover:bg-rose-100 focus:outline-none focus:ring-2 focus:ring-rose-400"
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
