import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Playwright owns e2e/; running it here would try to drive a browser.
    include: ["{app,lib}/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      // Show the fully covered files too; a silent 100% is still evidence.
      skipFull: false,
      include: ["{app,lib}/**/*.{ts,tsx}"],
      exclude: [
        // Generated from the OpenAPI schema; the contract check in
        // scripts/generate-api-client.sh is what guards it.
        "lib/api-types.ts",
        "app/layout.tsx",
        "**/*.test.{ts,tsx}",
        // Test infrastructure, not shipped code.
        "app/test-api.ts",
        "app/test-app.tsx",
      ],
      // Brief §6.2 sets the frontend floor at 80% line. These are the numbers
      // the suite actually reaches, kept a little under the measured value so
      // ordinary churn does not fail the gate, and never lowered: raising a
      // threshold is how a coverage gain is kept. Milestone 2.1 raised them
      // from 85/85/85/78 — the 1,863-line `app/Home.tsx` that dominated and
      // capped the total is gone, decomposed into components the tests reach.
      thresholds: {
        lines: 93,
        statements: 93,
        functions: 92,
        branches: 85,
      },
    },
  },
});
