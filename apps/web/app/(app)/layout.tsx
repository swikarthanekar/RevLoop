"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell/app-shell";
import { useAuthSession } from "@/lib/auth/session";

/**
 * Route guard for every page under (app).
 *
 * In dev/local/test mode (no Supabase configured), useAuthSession() always
 * reports "authenticated" -- see lib/auth/session.tsx -- so this never
 * redirects and behavior is unchanged from before Supabase auth existed.
 * Only a real deployment with Supabase configured enforces the redirect.
 */
export default function ShellLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = useAuthSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (session.status === "unauthenticated") {
      const next = encodeURIComponent(pathname);
      router.replace(`/login?next=${next}`);
    }
  }, [session.status, pathname, router]);

  if (session.status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-neutral-50">
        <p className="text-sm text-neutral-500">Loading…</p>
      </div>
    );
  }

  if (session.status === "unauthenticated") {
    // Redirect is in flight (see effect above); render nothing meanwhile.
    return null;
  }

  return <AppShell>{children}</AppShell>;
}
