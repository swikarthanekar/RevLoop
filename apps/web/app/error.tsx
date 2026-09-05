"use client";

import { useEffect } from "react";
import Link from "next/link";

import { APP_NAME } from "@/lib/constants";

/**
 * Route-level error boundary.
 *
 * Deliberately says nothing about what failed. The error object can carry
 * internal detail, and this page is reachable by anyone with the URL, so it
 * offers a recovery path instead of a diagnosis. The digest is safe to show —
 * Next.js generates it precisely so a user can quote it without exposing the
 * underlying message.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Server-side detail stays server-side; this is the browser console only.
    console.error("Unhandled route error", error);
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6 py-16 text-ink">
      <div className="w-full max-w-md">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
          {APP_NAME}
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">
          Something went wrong on this page
        </h1>
        <p className="mt-2 text-sm text-ink-muted">
          No recovery action was started or changed by this error. Try again, or
          return to the dashboard.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center rounded-md bg-accent px-3 py-2 text-sm font-medium text-on-accent hover:bg-accent-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
          >
            Try again
          </button>
          <Link
            href="/dashboard"
            className="inline-flex items-center rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
          >
            Go to dashboard
          </Link>
        </div>
        {error.digest ? (
          <p className="mt-6 border-t border-line pt-3 text-xs text-ink-muted">
            Reference: <span className="font-mono">{error.digest}</span>
          </p>
        ) : null}
      </div>
    </main>
  );
}
