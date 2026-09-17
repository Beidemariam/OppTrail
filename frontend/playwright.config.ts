import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.E2E_PORT ?? 8123);
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  // Every spec drives the same seeded database over one shared server, and
  // several of them write. Running them in one worker in file order keeps that
  // honest instead of papering over cross-test writes with retries.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Standard in containers: the sandbox runs unprivileged with all
        // capabilities dropped, so Chromium's own sandbox cannot start.
        // sandbox/README.md says to do this rather than add capabilities.
        launchOptions: { args: ["--no-sandbox"] },
      },
    },
  ],
  webServer: {
    command: "npm run build && ../scripts/e2e-server.sh",
    url: `${baseURL}/api/health`,
    timeout: 300_000,
    reuseExistingServer: !process.env.CI,
    stdout: "ignore",
    stderr: "pipe",
  },
});
