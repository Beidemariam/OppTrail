import { test } from "@playwright/test";
import {
  ALEX,
  DEFERRED_AXE_RULES,
  NORTHWIND,
  card,
  expectNoAccessibilityViolations,
  expectRuleIsStillDeferred,
  openTimeline,
  signIn,
} from "./helpers";

/**
 * axe on each major page, in both themes (brief §3.4; D-003's Phase 2
 * acceptance criterion: "light and dark themes both ship, and both pass axe
 * contrast checks on every component delivered in this phase").
 *
 * Each screen is audited twice, under an emulated `prefers-color-scheme` —
 * which is the real input `ThemeProvider` reads (`lib/theme.ts`), so this
 * exercises the same path a reader's desktop does rather than a test-only
 * switch. `color-contrast` is part of the audit from milestone 2.5 onwards:
 * the deferred list is empty.
 */
for (const colorScheme of ["light", "dark"] as const) {
  test.describe(`${colorScheme} theme`, () => {
    test.use({ colorScheme });

    test("the sign-in screen is accessible", async ({ page }) => {
      await page.goto("/");
      await expectNoAccessibilityViolations(page, `sign-in screen`);
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

    test("the search page is accessible", async ({ page }) => {
      await signIn(page, ALEX);
      await page.goto("/search?q=pricing");
      await expectNoAccessibilityViolations(page, "search results");
    });

    /** The three dialogs Phase 2 delivered, all on Radix from 2.5. */
    test("the command palette and the shortcut reference are accessible", async ({
      page,
    }) => {
      await signIn(page, ALEX);

      await page.getByRole("button", { name: /Search or jump to/ }).click();
      await expectNoAccessibilityViolations(page, "command palette");
      await page.keyboard.press("Escape");

      await page.keyboard.press("?");
      await expectNoAccessibilityViolations(page, "shortcut reference");
    });

    test("the confirmation dialog is accessible", async ({ page }) => {
      await signIn(page, ALEX);
      await card(page, NORTHWIND)
        .getByRole("button", { name: "Delete" })
        .click();

      await expectNoAccessibilityViolations(page, "confirmation dialog");
    });
  });
}

/**
 * The deferred-rule list is only honest while the rules on it still fail.
 * Milestone 2.5 emptied it, so this loop has nothing to check today — and the
 * moment an entry is added back, this is what proves it is a real failure
 * rather than a rule someone wanted quiet.
 */
test("every deferred axe rule is still a real failure", async ({ page }) => {
  await signIn(page, ALEX);
  for (const rule of DEFERRED_AXE_RULES) {
    await expectRuleIsStillDeferred(page, rule);
  }
});
