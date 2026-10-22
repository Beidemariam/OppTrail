import { expect, test, type Page } from "@playwright/test";
import {
  ALEX,
  expectNoAccessibilityViolations,
  entry,
  signIn,
} from "./helpers";

/**
 * Critical journey 13 (brief §6.3): keyboard-only — command palette, open an
 * opportunity, add a note. Milestone 2.4a is where the keyboard map exists to
 * walk, so it lands here.
 *
 * Every step after sign-in is driven by keystrokes alone. Nothing here clicks,
 * which is the assertion: `docs/UX.md` treats keyboard operation as a feature,
 * and a map that needs the mouse to reach half of it is not one.
 */

const MOD_K = "ControlOrMeta+k";
const MOD_ENTER = "ControlOrMeta+Enter";

/**
 * Tabs until the focused element carries `label`, so "reachable without a
 * mouse" is asserted rather than assumed. Bounded, so a control that is *not*
 * reachable fails with a sentence instead of hanging.
 */
async function tabTo(page: Page, name: string, limit = 60) {
  for (let step = 0; step < limit; step += 1) {
    // Either way a control can be named: a label, or its own text. The
    // composer's collapsed control is named by what it says (milestone 3.1).
    const focused = await page.evaluate(() => [
      document.activeElement?.getAttribute("aria-label"),
      document.activeElement?.textContent,
    ]);
    if (focused.includes(name)) {
      return;
    }
    await page.keyboard.press("Tab");
  }
  throw new Error(`"${name}" was not reachable by Tab within ${limit} stops`);
}

test("keyboard only: palette, opportunity, note", async ({ page }) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Keyboard ${suffix}`;

  await signIn(page, ALEX);

  // The reference is the discoverability of everything below it.
  await page.keyboard.press("?");
  const reference = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(reference).toBeVisible();
  await expect(reference.getByText("Open the command palette")).toBeVisible();
  await expectNoAccessibilityViolations(page, "the keyboard reference");
  await page.keyboard.press("Escape");
  await expect(reference).toBeHidden();

  // `c` composes an opportunity: the board's create form, focused without a
  // click. Value, currency and stage keep their defaults.
  await page.keyboard.press("c");
  await page.keyboard.type(opportunity);
  await page.keyboard.press("Tab");
  await page.keyboard.type("Keyboard Industries");
  await page.keyboard.press("Enter");
  await expect(
    page.locator("article.opportunity-card").filter({ hasText: opportunity }),
  ).toBeVisible();

  // The palette jumps to it by name.
  await page.keyboard.press(MOD_K);
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await expectNoAccessibilityViolations(page, "the command palette");

  await page.keyboard.type(opportunity);
  // The highlighted option is the jump; the search fallthrough sits below it
  // and carries the same words, so address it by position.
  const highlighted = palette.getByRole("option").first();
  await expect(highlighted).toContainText(opportunity);
  await expect(highlighted).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/\/opportunities\/\d+$/);
  await expect(
    page.locator(".record-header").getByRole("heading", { name: opportunity }),
  ).toBeVisible();

  // With a timeline open, `c` composes an entry instead, and Ctrl Enter
  // submits it from inside the form.
  await page.keyboard.press("c");
  await page.keyboard.type(`Pricing call ${suffix}`);
  await page.keyboard.press(MOD_ENTER);
  await expect(entry(page, `Pricing call ${suffix}`)).toBeVisible();

  // The note composer is reachable by Tab, and takes the same submit chord.
  // Collapsed it is one control (milestone 3.1); opening it puts the cursor in
  // the editor, so the note is written without touching the mouse or the
  // pointer-driven affordances.
  await tabTo(page, "Add note");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Add a note to this entry")).toBeFocused();
  await page.keyboard.type("Filed without touching the mouse.");
  await page.keyboard.press(MOD_ENTER);
  await expect(
    page.getByText("Filed without touching the mouse."),
  ).toBeVisible();

  await expectNoAccessibilityViolations(page, "a timeline reached by keyboard");
});

test("the board's cursor moves without a mouse", async ({ page }) => {
  await signIn(page, ALEX);

  // `j` from nothing lands on the first card in board order, and the card
  // itself takes focus rather than something inside it.
  await page.keyboard.press("j");
  const focusedCard = page.locator("article.opportunity-card:focus");
  await expect(focusedCard).toHaveCount(1);
  const first = await focusedCard.locator("h3").innerText();

  await page.keyboard.press("j");
  await expect(focusedCard.locator("h3")).not.toHaveText(first);

  await page.keyboard.press("k");
  await expect(focusedCard.locator("h3")).toHaveText(first);

  // Enter opens the card the cursor is on.
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/opportunities\/\d+$/);

  // `/` filters whichever screen you are on (R.1), so here it is the
  // timeline's keyword box. This asserted the *board's* until R.2 — the board
  // is not mounted on a deal's page any more, so it was passing on the race
  // between the keypress and React unmounting the screen behind it, and
  // failing in a full parallel run.
  //
  // The wait is part of the fix: a chord belongs to the screen that is open,
  // and one pressed before that screen has registered its listener is
  // dropped. A finger cannot hit that window; a test can.
  await expect(
    page.getByRole("button", { name: "Filter and order" }),
  ).toBeVisible();
  // ...and wait for the board to be *gone*, which is the other half of that
  // race. `/` is bound by whichever screen is open, and during a navigation
  // both are mounted for a moment -- so the board's handler could still win
  // and put the cursor in its own keyword box, on a screen about to unmount.
  // The deal's trigger appearing does not mean the board's has left.
  await expect(
    page.getByRole("button", { name: "+ Filter and sort" }),
  ).toHaveCount(0);
  await page.keyboard.press("/");
  await expect(page.getByLabel("Filter the timeline by keyword")).toBeFocused();
});

/** The same chord, meaning the same thing about a different screen (R.1). A
 *  test of its own rather than a second leg of the one above: leaving a text
 *  field by keyboard is its own little puzzle, and the chord is what is being
 *  tested here. */
test("/ filters the board when the board is the screen", async ({ page }) => {
  await signIn(page, ALEX);
  await expect(
    page.getByRole("button", { name: "+ Filter and sort" }),
  ).toBeVisible();

  await page.keyboard.press("/");

  await expect(
    page.getByLabel("Filter opportunities by keyword"),
  ).toBeFocused();
});

test("g sequences move between the board and search", async ({ page }) => {
  await signIn(page, ALEX);

  await page.keyboard.press("g");
  await page.keyboard.press("s");
  await expect(page.getByRole("heading", { name: "Search" })).toBeVisible();

  await page.keyboard.press("g");
  await page.keyboard.press("d");
  await expect(
    page.getByRole("heading", { name: "Opportunities" }),
  ).toBeVisible();
});
