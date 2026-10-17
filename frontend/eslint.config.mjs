import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

export default defineConfig([
  // Build and report output, none of which is source. `coverage/` arrived with
  // R.6's lcov reporter and brought a directory of generated JavaScript with
  // it, which eslint duly linted and complained about.
  globalIgnores([
    "out/**",
    "coverage/**",
    "playwright-report/**",
    "test-results/**",
  ]),
  ...nextVitals,
  ...nextTypescript,
]);
