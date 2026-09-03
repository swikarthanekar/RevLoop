import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Playwright owns e2e/*.spec.ts; Vitest must not collect them.
    exclude: ["node_modules/**", "dist/**", ".next/**", "e2e/**"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
