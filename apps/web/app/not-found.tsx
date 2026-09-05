import Link from "next/link";

import { APP_NAME } from "@/lib/constants";

/**
 * Branded 404.
 *
 * Without this file Next.js renders its own unstyled default — a bare `404`
 * heading on a white page that ignores the theme entirely, which is jarring
 * from inside a themed app and reads as a broken deployment rather than a
 * mistyped URL.
 */
export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6 py-16 text-ink">
      <div className="w-full max-w-md">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
          {APP_NAME}
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">
          This page doesn&rsquo;t exist
        </h1>
        <p className="mt-2 text-sm text-ink-muted">
          The link may be out of date, or the recovery case it pointed to may
          have been removed. Nothing has changed in your account.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <Link
            href="/dashboard"
            className="inline-flex items-center rounded-md bg-accent px-3 py-2 text-sm font-medium text-on-accent hover:bg-accent-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
          >
            Go to dashboard
          </Link>
          <Link
            href="/recovery"
            className="inline-flex items-center rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
          >
            Recovery opportunities
          </Link>
        </div>
      </div>
    </main>
  );
}
