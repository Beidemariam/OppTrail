import { expect, test, type Locator } from "@playwright/test";
import {
  card,
  expectNoAccessibilityViolations,
  createOpportunity,
  openTimeline,
  signOut,
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

/**
 * Milestone 3.0a: the three actions 2.4c left unbuilt (D-070's ruling) —
 * assign owner, add to view and export. Each writes to something different,
 * so the journey checks each against what it actually changed: the view's
 * filters, the record's ownership, and the file the link downloads.
 *
 * Signs up two users, because an ownership transfer needs somewhere to send
 * the deal.
 */
test("pins a selection into a view, exports it, and hands it to a colleague", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const first = `Handover first ${suffix}`;
  const second = `Handover second ${suffix}`;
  const heirEmail = `heir-${suffix}@opptrail.test`;

  await signUp(page, heirEmail, "Heir Apparent");
  await signOut(page);
  await signUp(page, `handover-${suffix}@opptrail.test`, "Handover Tester");

  for (const name of [first, second]) {
    await createOpportunity(page, name, { account: "Initech" });
  }

  // A view of the reader's own, which is the only kind "add to view" writes
  // to (D-106).
  await page
    .getByRole("button", { name: "Save current opportunity view" })
    .click();
  await page.getByLabel("View name").fill(`Shortlist ${suffix}`);
  await page.getByRole("button", { name: "Save view" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);

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

  // Export is a link, so the assertion is what the link answers with rather
  // than what it looks like: `page.request` carries the session cookie.
  const exportUrl = await bar
    .getByRole("link", { name: "Export CSV" })
    .getAttribute("href");
  const download = await page.request.get(exportUrl!);
  expect(download.status()).toBe(200);
  expect(download.headers()["content-disposition"]).toContain(
    "opportunities.csv",
  );
  const csv = await download.text();
  expect(csv.split("\n")[0]).toContain("account_name");
  expect(csv).toContain(first);
  expect(csv).toContain(second);

  const viewOption = await bar
    .getByLabel("Add to saved view")
    .locator("option")
    .nth(1)
    .getAttribute("value");
  await bar.getByLabel("Add to saved view").selectOption(viewOption!);
  await bar.getByRole("button", { name: "Add to view" }).click();
  await expect(page.locator(".toast").last()).toContainText(
    "2 opportunities added to the view.",
  );

  // Applying that view now draws the pinned pair and says so.
  await createOpportunity(page, `Unpinned ${suffix}`, { account: "Initech" });
  // By value: an option reads "<name> - <visibility>" since 2.13, so the
  // name alone is not the label.
  await page.getByLabel("Saved opportunity views").selectOption(viewOption!);
  // The pinned selection is a filter like any other since R.1, so it says so
  // as a chip and the chip is what removes it.
  await expect(page.getByRole("button", { name: /2 pinned/ })).toBeVisible();
  await expect(card(page, `Unpinned ${suffix}`)).toHaveCount(0);
  await page.getByRole("button", { name: /2 pinned/ }).click();
  await expect(card(page, `Unpinned ${suffix}`)).toBeVisible();

  // And the handover itself: owner-only, and the previous owner stays on as
  // an editor rather than losing the deal (D-105).
  await check(firstCheckbox);
  await bar.getByLabel("Assign owner by email").fill(heirEmail);
  await bar.getByRole("button", { name: "Assign owner" }).click();
  await expect(page.locator(".toast").last()).toContainText(
    "1 opportunity handed over.",
  );

  await page.reload();
  await openTimeline(page, first);
  await expect(page.locator(".opportunity-facts")).toContainText(
    "Your role: editor",
  );
  await expect(
    page.getByRole("article").filter({ hasText: "Owner changed to Heir" }),
  ).toBeVisible();
});
