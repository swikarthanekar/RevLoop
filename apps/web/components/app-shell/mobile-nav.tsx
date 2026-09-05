"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { APP_NAME } from "@/lib/constants";
import { PRIMARY_NAV_ITEMS } from "@/components/app-shell/nav-items";

/**
 * Navigation for viewports below `md`, where the sidebar is hidden.
 *
 * Without this there was no navigation at all under 768px: the sidebar is
 * `hidden md:flex` and nothing replaced it, so moving between Dashboard,
 * Recovery and Compliance on a phone meant typing URLs.
 *
 * Deliberately a plain disclosure rather than a modal dialog: the panel is
 * inline in the header flow, so it needs no focus trap, no scroll lock and no
 * portal, and it degrades correctly if JavaScript is slow to hydrate.
 */
export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Route change closes the menu; otherwise it stays open over the new page.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        !panelRef.current?.contains(target) &&
        !triggerRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="mobile-nav-panel"
        aria-label={open ? "Close navigation menu" : "Open navigation menu"}
        className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-line bg-surface text-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
      >
        {/* Decorative: the accessible name is on the button. */}
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        >
          {open ? (
            <>
              <path d="M5 5l10 10" />
              <path d="M15 5L5 15" />
            </>
          ) : (
            <>
              <path d="M3 6h14" />
              <path d="M3 10h14" />
              <path d="M3 14h14" />
            </>
          )}
        </svg>
      </button>

      <div
        id="mobile-nav-panel"
        ref={panelRef}
        hidden={!open}
        className="absolute left-0 right-0 top-full z-30 border-b border-line bg-surface shadow-lg"
      >
        <nav aria-label="Primary" className="px-3 py-3">
          <p className="px-2 pb-2 text-xs font-medium uppercase tracking-wide text-ink-muted">
            {APP_NAME}
          </p>
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
                    className={`block rounded-md px-3 py-2.5 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 ${
                      active
                        ? "bg-surface-active text-ink"
                        : "text-ink hover:bg-surface-hover"
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
      </div>
    </div>
  );
}
