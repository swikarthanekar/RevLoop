"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { APP_NAME } from "@/lib/constants";
import { PRIMARY_NAV_ITEMS } from "@/components/app-shell/nav-items";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-line bg-surface">
      <div className="border-b border-line px-4 py-4">
        <Link href="/dashboard" className="text-lg font-semibold tracking-tight text-ink">
          {APP_NAME}
        </Link>
        <p className="mt-1 text-xs text-ink-muted">Revenue recovery control plane</p>
      </div>
      <nav className="flex-1 px-2 py-4" aria-label="Primary">
        <ul className="space-y-1">
          {PRIMARY_NAV_ITEMS.map((item) => {
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`block rounded-md px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-neutral-400 ${
                    active
                      ? "bg-surface-active text-ink"
                      : "text-ink hover:bg-surface-hover hover:text-ink"
                  }`}
                >
                  {item.label}
                  {item.hint ? (
                    <span className="mt-0.5 block text-xs font-normal text-ink-muted">
                      {item.hint}
                    </span>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
