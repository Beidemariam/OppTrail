import { expect, test } from "@playwright/test";

import {
  ALEX,
  NORTHWIND,
  card,
  createOpportunity,
  expectNoAccessibilityViolations,
  openTimeline,
  signIn,
  signUp,
} from "./helpers";

/**
 * Automations (milestone 6.3, `docs/FEATURES.md` §11).
 *
 * What a rule does to the database is `backend/tests/test_automations.py`,
 * and how the screen renders an answer is `app/Automations.test.tsx`. What
 * this adds is the half neither reaches: a rule written through the real form,
 * previewed against real deals, and then applied — with the task it created
 * and the system entry naming the rule read back off the deal's own screen,
 * which is §11's traceability requirement seen from where a person would
 * actually meet it.
 */
async function openAutomations(page: Parameters<typeof signIn>[0]) {
  await page.getByRole("link", { name: "Automations" }).click();
  await expect(page).toHaveURL(/\/automations$/);
  await expect(
    page.getByRole("heading", { name: "Automations" }),
  ).toBeVisible();
}

test("a rule is written, previewed, and then applied", async ({ page }) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const name = `Chase the quiet ones ${suffix}`;

  await signIn(page, ALEX);
  await openAutomations(page);

  await page.getByRole("button", { name: "New rule" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(name);
  // The default trigger is the one §11 opens with: "if nothing has happened
  // in two weeks, remind me".
  await expect(dialog.getByLabel("Days", { exact: true })).toHaveValue("14");
  await dialog.getByLabel("Title").fill(`Follow up ${suffix}`);
  await dialog.getByRole("button", { name: "Create rule" }).click();

  // The rule reads back as a sentence, which is what §11 means by legible.
  const rule = page.locator(".automation-rule", { hasText: name });
  await expect(rule).toContainText(
    "When nothing has happened for 14 days, create a task for the deal's owner",
  );

  // Preview writes nothing, and says how much it looked at.
  await rule.getByRole("button", { name: "Preview" }).click();
  await expect(rule.locator(".automation-preview")).toContainText(
    /Preview: matched \d+ of \d+ deals/,
  );
  await expect(rule.locator(".automation-preview")).toContainText(
    "preview only; nothing was written",
  );

  await expectNoAccessibilityViolations(page, "automations");
});

test("an applied rule leaves a task and an entry naming it", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const name = `Log the silence ${suffix}`;

  await signIn(page, ALEX);
  await openAutomations(page);

  await page.getByRole("button", { name: "New rule" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(name);
  await dialog.getByLabel("Days", { exact: true }).fill("1");
  await dialog.getByLabel("Action").selectOption("add_entry");
  await dialog.getByLabel("Title").fill(`Nothing has happened ${suffix}`);
  await dialog.getByRole("button", { name: "Create rule" }).click();

  const rule = page.locator(".automation-rule", { hasText: name });
  // Running for real asks first, because it writes to deals that are not on
  // this screen.
  await rule.getByRole("button", { name: "Run now" }).click();
  await page.getByRole("button", { name: "Run it" }).click();

  await expect(rule.locator(".automation-preview")).toContainText(
    /Ran: matched \d+ of \d+ deals/,
  );
  await expect(rule.locator(".automation-outcome").first()).toHaveText(
    "applied",
  );

  // The log is a disclosure, and it is where a skip would be read.
  await rule.getByRole("button", { name: /What it has done/ }).click();
  await expect(rule.locator(".automation-runs")).toBeVisible();

  // §11: the automated write left an entry naming the rule, on the deal it
  // acted on. Addressed by following the run log's own link, because which
  // deals were quiet depends on the seed.
  const touched = rule.locator(".automation-runs a").first();
  await touched.click();
  await expect(
    page.getByText(`Nothing has happened ${suffix}`).first(),
  ).toBeVisible();
  await expect(
    page.getByText(`Automation rule "${name}" did this.`),
  ).toBeVisible();
});

test("a rule somebody else wrote is visible and not operable", async ({
  page,
}) => {
  // D-173: a colleague's rule can move a deal you own, so it has to be
  // readable; the API refuses the writes, so the screen offers none.
  const suffix = Math.random().toString(36).slice(2, 8);
  const name = `Alex's own rule ${suffix}`;

  await signIn(page, ALEX);
  await openAutomations(page);
  await page.getByRole("button", { name: "New rule" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(name);
  await dialog.getByLabel("Title").fill("Chase it");
  await dialog.getByRole("button", { name: "Create rule" }).click();
  await expect(
    page.locator(".automation-rule", { hasText: name }),
  ).toBeVisible();

  // Sign out lives in the board's top bar, not in this screen's own header
  // (the shape `/reports` and `/tasks` have).
  await page.getByRole("link", { name: "Opportunities" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await signUp(page, `rules-${suffix}@opptrail.test`, "New Reader");
  await openAutomations(page);

  const theirs = page.locator(".automation-rule", { hasText: name });
  await expect(theirs).toContainText("Alex's");
  await expect(theirs.getByRole("button", { name: "Preview" })).toHaveCount(0);
  await expect(theirs.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await expect(theirs.getByRole("button", { name: "Archive" })).toHaveCount(0);
});

test("the deal's owner can clear up an entry a rule wrote", async ({
  page,
}) => {
  // Milestone 6.3a, D-181, the human's request at the 6.3 review: a mistaken
  // rule leaves entries behind and somebody has to be able to remove them.
  // Before this, every system entry answered 403 to everybody.
  //
  // This test owns its account and its deal, which is the lesson of two
  // failures getting here: triggered by silence it depended on the seeded
  // deals still being quiet (which the test above stops being true), and
  // moved to a named stage it depended on which stage the seed left Northwind
  // in (Qualification -- so "move to Qualification" wrote nothing at all).
  const suffix = Math.random().toString(36).slice(2, 8);
  const name = `Clear me up ${suffix}`;
  const deal = `Rule cleanup ${suffix}`;

  await signUp(page, `cleanup-${suffix}@opptrail.test`, "Cleanup Tester");
  await createOpportunity(page, deal, { stage: "Prospecting" });

  await openAutomations(page);
  await page.getByRole("button", { name: "New rule" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(name);
  await dialog.getByLabel("Trigger").selectOption("stage_changed");
  await dialog.getByLabel("Action").selectOption("add_entry");
  await dialog.getByLabel("Title").fill(`Written in error ${suffix}`);
  await dialog.getByRole("button", { name: "Create rule" }).click();
  await expect(
    page.locator(".automation-rule", { hasText: name }),
  ).toBeVisible();

  // The human write that wakes it: the move-to-stage select, which is the
  // keyboard-operable half of the board's drag (milestone 2.7).
  await page.getByRole("link", { name: "Opportunities" }).click();
  await card(page, deal)
    .getByLabel(`Move ${deal} to stage`)
    .selectOption("Qualification");
  await openTimeline(page, deal);

  const entry = page
    .locator("article", { hasText: `Written in error ${suffix}` })
    .first();
  await expect(entry).toBeVisible({ timeout: 15000 });
  // Badged as an automation, and Delete offered where Edit is not. Addressed
  // by the badge's own class: the body says `Automation rule "..." did this`,
  // so a text query for "Automation" matches twice.
  await expect(entry.locator(".system-badge")).toHaveText("Automation");
  await expect(entry.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await entry.getByRole("button", { name: "Delete" }).click();

  await expect(page.getByText(`Written in error ${suffix}`)).toHaveCount(0);
  // Undoable, like every other delete in this app.
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(
    page.getByText(`Written in error ${suffix}`).first(),
  ).toBeVisible();
});

test("a system entry a person caused still offers nothing", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await page.goto("/");
  await page
    .getByRole("link", { name: "Northwind platform rollout" })
    .first()
    .click();

  const created = page
    .locator("article", { hasText: "Opportunity created" })
    .first();
  await expect(created.getByText("System")).toBeVisible();
  await expect(created.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await expect(created.getByRole("button", { name: "Delete" })).toHaveCount(0);
});

test("a field the browser refuses says what to fix", async ({ page }) => {
  // Milestone 6.5a, D-184 — the human's finding at the 6.5 review: *"Doesn't
  // take in words for number of days, except for some reason the letter e,
  // and it doesn't say what to fix."*
  //
  // Here rather than only in a component test because the *wording* is the
  // browser's own and jsdom's is not Chrome's. This asserts the real
  // sentence a person reads.
  await signIn(page, ALEX);
  await openAutomations(page);
  await page.getByRole("button", { name: "New rule" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill("Letter days");
  await dialog.getByLabel("Title").fill("Chase it");

  const days = dialog.getByLabel("Days", { exact: true });
  await days.fill("");
  // A number input keeps `e` on screen -- it is legal in `1e5` -- while
  // reporting its value as empty with `badInput` set. Before this milestone
  // the browser cancelled the submit, showed a tooltip that vanished, and
  // nothing in the app said anything at all.
  await days.type("e");
  await dialog.getByRole("button", { name: "Create rule" }).click();

  await expect(dialog.getByText("Please enter a number.")).toBeVisible();
  await expect(days).toHaveAttribute("aria-invalid", "true");
  await expect(dialog).toBeVisible();

  // And it goes away when corrected, rather than needing the form reopened.
  await days.fill("14");
  await dialog.getByRole("button", { name: "Create rule" }).click();
  await expect(dialog).toHaveCount(0);
});
