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
        "app/test-editor.ts",
      ],
      // Brief §6.2 sets the frontend floor at 80% line. These are the numbers
      // the suite actually reaches, kept a little under the measured value so
      // ordinary churn does not fail the gate, and never lowered: raising a
      // threshold is how a coverage gain is kept. Milestone 2.1 raised them
      // from 85/85/85/78 — the 1,863-line `app/Home.tsx` that dominated and
      // capped the total is gone, decomposed into components the tests reach.
      // Milestone 2.4a raised them again, from 93/93/92/85, against a measured
      // 97.03 lines / 97.10 statements / 95.67 functions / 89.59 branches.
      // Milestone 2.5 raised them from 94/94/93/87: the theme, the contrast
      // tokens and the confirmation dialog all arrived with their own tests.
      // Milestone 2.8 raised branches and functions from 88/94, against a
      // measured 96.88 statements / 90.18 branches / 95.59 functions / 96.85
      // lines — the table, the calendar and the density preference each
      // arrived with their own tests, and the two view components are covered
      // outright.
      // Milestone 2.11 raised branches from 89, against a measured 97.10
      // statements / 90.95 branches / 95.80 functions / 97.07 lines:
      // `app/InlineEdit.tsx` arrived fully covered, including the values it
      // refuses. The other three stay where 2.8 put them — the measured line
      // and statement figures are 97.1 against a 96 floor, and a floor set
      // one tenth under the measurement fails on ordinary churn rather than
      // on a regression.
      thresholds: {
        lines: 96,
        statements: 96,
        functions: 95,
        branches: 90,
      },
    },
  },
});
