import { expect, test, type Locator } from "@playwright/test";
import {
  card,
  expectNoAccessibilityViolations,
  createOpportunity,
  signUp,
} from "./helpers";

/**
 * Checks a bulk-selection checkbox, retrying the click itself rather than
 * just the assertion after it.
 *
 * Investigated rather than assumed: a raw CDP mouse sequence at the same,
 * already-settled coordinates toggles the checkbox every time, and the
 * app's own change handler fires correctly whenever the click actually
 * lands, so this is not the application failing to register a click — it is
 * Playwright's click occasionally resolving its scroll-adjusted coordinate
 * for a row this far down the page before the scroll (also triggered by the
 * same action) has fully settled. Retrying the click is the accommodation
 * for that, not a mask over broken behaviour.
 */
async function check(checkbox: Locator) {
  await expect(async () => {
    await checkbox.scrollIntoViewIfNeeded();
    await checkbox.click();
    await expect(checkbox).toBeChecked();
  }).toPass();
}

/**
 * Milestone 2.4c: multi-select on the board, the action bar that replaces
 * the filter bar while a selection is live, and the transactional bulk
 * endpoint behind it (`docs/UX.md`).
 *
 * Signs up rather than using a seeded user: this test deletes opportunities,
 * and the other specs read the seeded ones.
 */
test("checks two cards, bulk-changes their stage, then bulk-deletes with Undo", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const first = `Bulk first ${suffix}`;
  const second = `Bulk second ${suffix}`;

  await signUp(page, `bulk-${suffix}@opptrail.test`, "Bulk Tester");

  for (const name of [first, second]) {
    await createOpportunity(page, name, { account: "Initech" });
  }

  const firstCheckbox = card(page, first).getByLabel(
    `Select ${first} for bulk actions`,
  );
  const secondCheckbox = card(page, second).getByLabel(
    `Select ${second} for bulk actions`,
  );
  await check(firstCheckbox);
  await check(secondCheckbox);

  const bar = page.getByRole("toolbar", { name: "Bulk actions" });
  await expect(bar).toContainText("2 selected");
  await expect(page.getByRole("button", { name: "Apply" })).toHaveCount(0);
  await expectNoAccessibilityViolations(
    page,
    "the board with the bulk action bar open",
  );

  await bar.getByLabel("Change stage to").selectOption("Closed Won");
  await bar.getByRole("button", { name: "Change stage" }).click();

  await expect(page.locator(".toast")).toContainText(
    "2 opportunities updated.",
  );
  const closedWon = page
    .locator(".stage-column")
    .filter({ has: page.getByRole("heading", { name: "Closed Won" }) });
  // By the card's own link: the name also appears in the move-to-stage
  // control's hidden label (milestone 2.7).
  await expect(closedWon.getByRole("link", { name: first })).toBeVisible();
  await expect(closedWon.getByRole("link", { name: second })).toBeVisible();
  // A successful bulk action clears the selection, so the filter bar is
  // back rather than the action bar.
  await expect(page.getByRole("toolbar", { name: "Bulk actions" })).toHaveCount(
    0,
  );

  await check(firstCheckbox);
  await check(secondCheckbox);

  // Bulk delete shares the typed confirmation the single delete has had since
  // milestone 2.5 (`app/ConfirmDialog.tsx`). Several at once are confirmed by
  // the word rather than by a name, since no one name describes what goes.
  await bar.getByRole("button", { name: "Delete" }).click();
  const confirmation = page.getByRole("alertdialog");
  await expect(
    confirmation.getByRole("button", { name: "Delete opportunities" }),
  ).toBeDisabled();
  await confirmation.getByRole("textbox").fill("delete");
  await confirmation
    .getByRole("button", { name: "Delete opportunities" })
    .click();

  await expect(card(page, first)).toHaveCount(0);
  await expect(card(page, second)).toHaveCount(0);
  // The stage change raised a toast of its own a moment ago and toasts last
  // ten seconds, so this is the newest one rather than the only one.
  const toast = page.locator(".toast").last();
  await expect(toast).toContainText("2 opportunities deleted.");

  await toast.getByRole("button", { name: "Undo" }).click();
  await expect(card(page, first)).toBeVisible();
  await expect(card(page, second)).toBeVisible();

  // The restore reached the database, not just the cache.
  await page.reload();
  await expect(card(page, first)).toBeVisible();
  await expect(card(page, second)).toBeVisible();
});
