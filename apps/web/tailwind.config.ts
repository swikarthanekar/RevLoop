import type { Config } from "tailwindcss";

export default {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        ink: {
          950: "#05070d",
          900: "#0a0e1a",
          800: "#111726",
          700: "#1a2236",
          600: "#252f47",
          500: "#374260",
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "Arial", "Helvetica", "sans-serif"],
        display: ["var(--font-display)", "var(--font-geist-sans)", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      boxShadow: {
        glass: "0 1px 0 0 rgba(255,255,255,0.06) inset, 0 20px 60px -20px rgba(0,0,0,0.45)",
        "glass-sm": "0 1px 0 0 rgba(255,255,255,0.05) inset, 0 10px 30px -12px rgba(0,0,0,0.35)",
        premium:
          "0 1px 0 0 rgba(255,255,255,0.7) inset, 0 12px 32px -14px rgba(15,23,42,0.18)",
      },
      backgroundImage: {
        "mesh-ink":
          "radial-gradient(60% 50% at 15% 10%, rgba(99,102,241,0.35), transparent 60%), radial-gradient(50% 40% at 85% 0%, rgba(16,185,129,0.25), transparent 60%), radial-gradient(60% 60% at 50% 100%, rgba(217,70,239,0.12), transparent 60%)",
        "grid-fade":
          "linear-gradient(to bottom, rgba(255,255,255,0.06), transparent 70%)",
      },
      keyframes: {
        "gradient-shift": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-6px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "gradient-shift": "gradient-shift 8s ease infinite",
        float: "float 6s ease-in-out infinite",
        shimmer: "shimmer 2.5s linear infinite",
      },
      backgroundSize: {
        "gradient-xl": "200% 200%",
      },
    },
  },
  plugins: [],
} satisfies Config;
