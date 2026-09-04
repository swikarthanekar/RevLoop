"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuthSession } from "@/lib/auth/session";
import { getSupabaseClient } from "@/lib/auth/supabase-client";
import { getDemoLoginCredentials, isSupabaseConfigured } from "@/lib/config/public";

const DEFAULT_REDIRECT = "/dashboard";

/** Only ever redirect within the app -- never follow an external `next` value. */
function safeRedirectTarget(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) {
    return DEFAULT_REDIRECT;
  }
  return raw;
}

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const session = useAuthSession();
  const redirectTarget = safeRedirectTarget(searchParams.get("next"));

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already signed in (e.g. opened /login directly with a live session):
  // leave immediately rather than showing the form.
  useEffect(() => {
    if (session.status === "authenticated") {
      router.replace(redirectTarget);
    }
  }, [session.status, redirectTarget, router]);

  if (!isSupabaseConfigured()) {
    return (
      <div className="rounded-md border border-neutral-200 bg-white p-4 text-sm text-neutral-700">
        <p className="font-medium text-neutral-900">Sign-in is not required here.</p>
        <p className="mt-1">
          This environment authenticates via the configured development
          token, not Supabase. If the dashboard shows an authentication
          error, check <code className="font-mono text-xs">NEXT_PUBLIC_DEV_AUTH_TOKEN</code>.
        </p>
        <a
          href="/dashboard"
          className="mt-3 inline-flex items-center rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50"
        >
          Go to dashboard
        </a>
      </div>
    );
  }

  async function signIn(
    credentials: { email: string; password: string },
    invalidCredentialsMessage: string,
  ) {
    if (submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const { error: signInError } =
        await getSupabaseClient().auth.signInWithPassword(credentials);
      if (signInError) {
        setError(invalidCredentialsMessage);
        return;
      }
      router.replace(redirectTarget);
    } catch {
      setError("Unable to reach the authentication service. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void signIn({ email: email.trim(), password }, "Incorrect email or password.");
  }

  const demoCredentials = getDemoLoginCredentials();

  function handleDemoSignIn() {
    if (!demoCredentials) {
      return;
    }
    void signIn(
      demoCredentials,
      "Demo sign-in is temporarily unavailable. Use email/password below.",
    );
  }

  return (
    <div className="space-y-5">
      {demoCredentials ? (
        <div>
          <button
            type="button"
            onClick={handleDemoSignIn}
            disabled={submitting}
            aria-busy={submitting}
            className="inline-flex w-full items-center justify-center rounded-md border border-neutral-900 bg-white px-3 py-2 text-sm font-medium text-neutral-900 hover:bg-neutral-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Signing in…" : "Continue as demo"}
          </button>
          <p className="mt-1.5 text-center text-xs text-neutral-500">
            Signs in with a shared, read/write demo account — synthetic data
            and Razorpay Test Mode only.
          </p>
          <div className="my-4 flex items-center gap-3 text-xs text-neutral-400">
            <span className="h-px flex-1 bg-neutral-200" />
            or sign in
            <span className="h-px flex-1 bg-neutral-200" />
          </div>
        </div>
      ) : null}

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div>
          <label htmlFor="login-email" className="block text-sm font-medium text-neutral-700">
            Email
          </label>
          <input
            id="login-email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
          />
        </div>

        <div>
          <label htmlFor="login-password" className="block text-sm font-medium text-neutral-700">
            Password
          </label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
          />
        </div>

        {error ? (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          aria-busy={submitting}
          className="inline-flex w-full items-center justify-center rounded-md bg-neutral-900 px-3 py-2 text-sm font-medium text-white hover:bg-neutral-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
