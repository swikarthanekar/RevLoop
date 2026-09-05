import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "var(--canvas)",
        surface: {
          DEFAULT: "var(--surface)",
          hover: "var(--surface-hover)",
          active: "var(--surface-active)",
        },
        ink: {
          DEFAULT: "var(--ink)",
          muted: "var(--ink-muted)",
        },
        line: "var(--line)",
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
        },
        "on-accent": "var(--on-accent)",
        // Status colors resolve through CSS variables so a single class works
        // in both themes; see the note in app/globals.css.
        success: {
          surface: "var(--success-surface)",
          border: "var(--success-border)",
          ink: "var(--success-ink)",
          "ink-strong": "var(--success-ink-strong)",
        },
        warning: {
          surface: "var(--warning-surface)",
          border: "var(--warning-border)",
          ink: "var(--warning-ink)",
        },
        danger: {
          surface: "var(--danger-surface)",
          border: "var(--danger-border)",
          ink: "var(--danger-ink)",
        },
        info: {
          surface: "var(--info-surface)",
          border: "var(--info-border)",
          ink: "var(--info-ink)",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
