import { expect, test } from "@playwright/test";
import { ALEX, signIn } from "./helpers";

/**
 * Light and dark, as a reader meets them (milestone 2.5, D-003).
 *
 * The contrast half of this is `07-accessibility.spec.ts`, which audits every
 * screen under both schemes. What is here is the switch itself: the system
 * preference is followed, an explicit choice overrides it, and the choice
 * survives a reload — the three things that make "both themes ship" true
 * rather than a stylesheet nobody can reach.
 */

test.describe("following the system", () => {
  test.use({ colorScheme: "dark" });

  test("paints dark without being asked", async ({ page }) => {
    await signIn(page, ALEX);

    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.getByLabel("Theme")).toHaveValue("system");
  });
});

test.describe("choosing for yourself", () => {
  test.use({ colorScheme: "light" });

  test("holds dark against a light system, across a reload", async ({
    page,
  }) => {
    await signIn(page, ALEX);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

    await page.getByLabel("Theme").selectOption("dark");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.getByLabel("Theme")).toHaveValue("dark");

    // And can be handed back to the system, which is still light.
    await page.getByLabel("Theme").selectOption("system");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });
});
