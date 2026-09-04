"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { APP_NAME } from "@/lib/constants";
import { PRIMARY_NAV_ITEMS } from "@/components/app-shell/nav-items";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col bg-ink-950 text-neutral-200">
      <div className="border-b border-white/10 px-4 py-4">
        <Link
          href="/dashboard"
          className="flex items-center gap-2.5 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
        >
          <span
            aria-hidden="true"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-400 via-cyan-400 to-emerald-400 text-sm font-bold text-ink-950 shadow-glass-sm"
          >
            R
          </span>
          <span className="font-display text-lg font-semibold tracking-tight text-white">
            {APP_NAME}
          </span>
        </Link>
        <p className="mt-2 text-xs text-neutral-400">Revenue recovery control plane</p>
      </div>
      <nav className="flex-1 px-2 py-4" aria-label="Primary">
        <ul className="space-y-1">
          {PRIMARY_NAV_ITEMS.map((item) => {
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400 ${
                    active
                      ? "bg-white/10 text-white"
                      : "text-neutral-300 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <Icon
                    aria-hidden="true"
                    className={`h-4 w-4 shrink-0 ${
                      active ? "text-cyan-300" : "text-neutral-500 group-hover:text-neutral-300"
                    }`}
                    strokeWidth={2}
                  />
                  <span className="flex-1">
                    {item.label}
                    {item.hint ? (
                      <span className="mt-0.5 block text-xs font-normal text-neutral-500">
                        {item.hint}
                      </span>
                    ) : null}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
