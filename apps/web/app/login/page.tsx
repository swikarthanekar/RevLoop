import { Suspense } from "react";
import type { Metadata } from "next";

import { LoginForm } from "@/app/login/login-form";

export const metadata: Metadata = {
  title: "Sign in | RevLoop",
};

export default function LoginPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-ink-950 px-4">
      <div className="absolute inset-0 bg-mesh-ink" aria-hidden="true" />
      <div className="absolute inset-0 bg-grid-fade" aria-hidden="true" />

      <div className="relative w-full max-w-sm space-y-6">
        <div className="text-center">
          <span
            aria-hidden="true"
            className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-400 via-cyan-400 to-emerald-400 font-display text-lg font-bold text-ink-950 shadow-glass-sm"
          >
            R
          </span>
          <h1 className="mt-3 font-display text-xl font-semibold tracking-tight text-white">
            RevLoop
          </h1>
          <p className="mt-1 text-sm text-neutral-400">
            AI revenue recovery control plane
          </p>
        </div>
        <div className="glass-panel-dark p-6">
          <Suspense fallback={null}>
            <LoginForm />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
