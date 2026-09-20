import { expect, test, type Locator } from "@playwright/test";
import {
  card,
  expectNoAccessibilityViolations,
  opportunityForm,
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

  const form = opportunityForm(page);
  for (const name of [first, second]) {
    await form.getByLabel("Opportunity").fill(name);
    await form.getByLabel("Account").fill("Initech");
    await form.getByRole("button", { name: "Create opportunity" }).click();
    await expect(card(page, name)).toBeVisible();
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
  await expect(closedWon.getByText(first)).toBeVisible();
  await expect(closedWon.getByText(second)).toBeVisible();
  // A successful bulk action clears the selection, so the filter bar is
  // back rather than the action bar.
  await expect(page.getByRole("toolbar", { name: "Bulk actions" })).toHaveCount(
    0,
  );

  await check(firstCheckbox);
  await check(secondCheckbox);

  // No typed prompt like the single-opportunity delete's (2.5's scope);
  // `window.confirm` is still the gate bulk delete shares with it
  // (`lib/confirm.ts`).
  page.once("dialog", (dialog) => dialog.accept());
  await bar.getByRole("button", { name: "Delete" }).click();

  await expect(card(page, first)).toHaveCount(0);
  await expect(card(page, second)).toHaveCount(0);
  const toast = page.locator(".toast");
  await expect(toast).toContainText("2 opportunities deleted.");

  await toast.getByRole("button", { name: "Undo" }).click();
  await expect(card(page, first)).toBeVisible();
  await expect(card(page, second)).toBeVisible();

  // The restore reached the database, not just the cache.
  await page.reload();
  await expect(card(page, first)).toBeVisible();
  await expect(card(page, second)).toBeVisible();
});
