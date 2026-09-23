import { expect, test } from "@playwright/test";
import {
  addNote,
  addComment,
  entry,
  entryForm,
  expectNoAccessibilityViolations,
  openTimeline,
  createOpportunity,
  signUp,
} from "./helpers";

/**
 * Milestone 2.4b: destructive actions apply and offer Undo instead of
 * confirming (`docs/UX.md`). The point of the journey is that the way back is
 * a real restore — the same row, still carrying its notes — so it survives a
 * reload, which a re-create in the client would not.
 *
 * Signs up rather than using a seeded user: this test deletes things, and the
 * other specs read the seeded opportunities.
 */
test("a deleted entry comes back, with its note, and stays back", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Undo ${suffix}`;

  await signUp(page, `undo-${suffix}@opptrail.test`, "Undo Tester");
  await createOpportunity(page, opportunity, {
    account: "Initech",
    value: "42000",
    currency: "USD",
  });
  await openTimeline(page, opportunity);

  await entryForm(page).getByLabel("Title").fill("Security review");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  const review = entry(page, "Security review");
  await expect(review).toBeVisible();

  await addNote(review, "They asked about SOC 2.");
  await expect(review).toContainText("They asked about SOC 2.");

  // No dialog: the entry goes, and the toast is the way back.
  await review.getByRole("button", { name: "Delete" }).first().click();
  await expect(
    page.getByRole("heading", { name: "Security review" }),
  ).toHaveCount(0);
  const toast = page.locator(".toast");
  await expect(toast).toContainText("Timeline entry deleted.");
  await expectNoAccessibilityViolations(
    page,
    "the timeline with an undo toast",
  );

  await toast.getByRole("button", { name: "Undo" }).click();
  await expect(
    page.getByRole("heading", { name: "Security review" }),
  ).toBeVisible();
  await expect(entry(page, "Security review")).toContainText(
    "They asked about SOC 2.",
  );

  // The restore reached the database, not just the cache.
  await page.reload();
  await expect(
    entry(page, "Security review").getByText("They asked about SOC 2."),
  ).toBeVisible();
});

test("an undone deletion is both events in the owner's audit log", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Audit ${suffix}`;

  await signUp(page, `undo-audit-${suffix}@opptrail.test`, "Audit Tester");
  await createOpportunity(page, opportunity, { account: "Initech" });
  await openTimeline(page, opportunity);

  await entryForm(page).getByLabel("Title").fill("Reference call");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  const call = entry(page, "Reference call");
  await expect(call).toBeVisible();

  await call.getByRole("button", { name: "Delete" }).first().click();
  await page.locator(".toast").getByRole("button", { name: "Undo" }).click();
  await expect(
    page.getByRole("heading", { name: "Reference call" }),
  ).toBeVisible();

  // Undo does not erase the delete: the log is what happened, in order
  // (`AGENTS.md`, auditability).
  await page.locator(".audit-panel summary").click();
  const log = page.locator(".audit-list");
  await expect(log).toContainText("timeline_entry_deleted");
  await expect(log).toContainText("timeline_entry_restored");
});

test("deleting a note and a comment both leave an audit trail", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Note audit ${suffix}`;

  await signUp(page, `note-audit-${suffix}@opptrail.test`, "Note Audit Tester");
  await createOpportunity(page, opportunity, { account: "Initech" });
  await openTimeline(page, opportunity);

  await entryForm(page).getByLabel("Title").fill("Renewal call");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  const call = entry(page, "Renewal call");
  await expect(call).toBeVisible();

  await addNote(call, "Discussed pricing.");
  const note = page
    .locator("section.note-block")
    .filter({ hasText: "Discussed pricing." });
  await expect(note).toBeVisible();

  await addComment(note, "Following up next week.");
  const comment = note
    .locator(".comment-row")
    .filter({ hasText: "Following up next week." });
  await expect(comment).toBeVisible();

  await comment.getByRole("button", { name: "Delete" }).click();
  await expect(comment).toHaveCount(0);

  await note.getByRole("button", { name: "Delete" }).click();
  await expect(note).toHaveCount(0);

  await page.locator(".audit-panel summary").click();
  const log = page.locator(".audit-list");
  await expect(log).toContainText("comment_deleted");
  await expect(log).toContainText("note_deleted");
});
