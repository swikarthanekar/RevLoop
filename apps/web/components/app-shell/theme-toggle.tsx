"use client";

import { type Theme, useTheme } from "@/lib/theme/theme-provider";

const OPTIONS: { value: Theme; label: string; icon: string }[] = [
  { value: "light", label: "Light theme", icon: "☀️" },
  { value: "dark", label: "Dark theme", icon: "🌙" },
  { value: "system", label: "Match system theme", icon: "🖥️" },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Color theme"
      className="flex items-center gap-0.5 rounded-md border border-line bg-surface p-0.5"
    >
      {OPTIONS.map((option) => {
        const active = theme === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={option.label}
            title={option.label}
            onClick={() => setTheme(option.value)}
            className={`rounded px-2 py-1 text-xs leading-none focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400 ${
              active ? "bg-accent text-on-accent" : "text-ink-muted hover:bg-surface-hover"
            }`}
          >
            <span aria-hidden="true">{option.icon}</span>
          </button>
        );
      })}
    </div>
  );
}
