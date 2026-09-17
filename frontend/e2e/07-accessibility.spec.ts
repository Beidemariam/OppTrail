import { test } from "@playwright/test";
import {
  ALEX,
  DEFERRED_AXE_RULES,
  NORTHWIND,
  expectNoAccessibilityViolations,
  expectRuleIsStillDeferred,
  openTimeline,
  signIn,
} from "./helpers";

/**
 * axe on each major page (brief §3.4: "Playwright E2E with axe accessibility
 * checks"). Phase F ships the check; brief §8 (Phase R) is where the full
 * WCAG 2.1 AA sweep, focus management and keyboard operability land.
 */
test("the sign-in screen is accessible", async ({ page }) => {
  await page.goto("/");
  await expectNoAccessibilityViolations(page, "sign-in screen");
});

test("the dashboard is accessible", async ({ page }) => {
  await signIn(page, ALEX);
  await expectNoAccessibilityViolations(page, "dashboard");
});

test("the timeline, sharing panel and AI sidebar are accessible", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);
  await expectNoAccessibilityViolations(page, "timeline panel");
});

test("the notification panel is accessible", async ({ page }) => {
  await signIn(page, ALEX);
  await page.getByRole("button", { name: "Notifications" }).click();
  await expectNoAccessibilityViolations(page, "notification panel");
});

/**
 * The deferred-rule list is only honest while the rules on it still fail. Once
 * milestone 2.5 / R.2 fixes the palette this test starts failing, which is the
 * signal to delete the entry and tighten the gate.
 */
test("every deferred axe rule is still a real failure", async ({ page }) => {
  await signIn(page, ALEX);
  for (const rule of DEFERRED_AXE_RULES) {
    await expectRuleIsStillDeferred(page, rule);
  }
});
