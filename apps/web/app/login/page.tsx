import { Suspense } from "react";
import type { Metadata } from "next";

import { LoginForm } from "@/app/login/login-form";

export const metadata: Metadata = {
  title: "Sign in | RevLoop",
};

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-lg font-semibold text-ink">RevLoop</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Revenue recovery control plane
          </p>
        </div>
        <div className="rounded-lg border border-line bg-surface p-6 shadow-sm">
          <Suspense fallback={null}>
            <LoginForm />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
