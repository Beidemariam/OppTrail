import { expect, test } from "@playwright/test";
import {
  addNote,
  entry,
  entryForm,
  openEntryForm,
  openHistory,
  openTimeline,
  createOpportunity,
  signUp,
} from "./helpers";

/**
 * Critical journey 3 (brief §6.3): edit a note, see the edit marker, and find
 * the previous text in the revision history — plus the other two histories
 * milestone 2.10 added beside it, and the restore milestone 3.1c added under
 * them.
 *
 * Driven entirely through the UI since 2.10, and through *one* destination
 * since 3.1c: the per-item History buttons and the sharing panel's audit
 * disclosure were folded into the opportunity's own history, where an edit
 * row opens onto what it changed (D-121). Owner-only rows, and the signed-up
 * user here owns what they create.
 */
test("editing a note marks it as edited and keeps the previous version", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Revision log ${suffix}`;

  await signUp(page, `history-${suffix}@opptrail.test`, "History Tester");
  await createOpportunity(page, opportunity, {
    account: "Cyberdyne",
    value: "15000",
    currency: "USD",
  });
  await openTimeline(page, opportunity);

  await openEntryForm(page);
  await entryForm(page).getByLabel("Title").fill("Pricing conversation");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  await expect(
    page.getByRole("heading", { name: "Pricing conversation" }),
  ).toBeVisible();

  const pricing = entry(page, "Pricing conversation");
  await addNote(pricing, "First draft of the pricing summary.");

  // Addressed by position, not by its text: the text is about to change, and a
  // text filter would stop matching the moment the note is retyped.
  const note = pricing.locator("section.note-block").first();
  await expect(note).toContainText("First draft of the pricing summary.");
  await expect(note.getByText("edited")).toHaveCount(0);

  await note.getByRole("button", { name: "Edit" }).click();
  await note
    .getByLabel("Edit this note")
    .fill("Second draft, with the 8% discount.");
  await note.getByRole("button", { name: "Save" }).click();

  await expect(note).toContainText("Second draft, with the 8% discount.");
  await expect(note.getByText("edited")).toBeVisible();

  const dialog = await openHistory(page);
  const edit = dialog
    .locator("li.activity-event")
    .filter({ hasText: "changed Body on a note" });
  await expect(edit).toHaveCount(1);

  // Nothing about what changed is fetched until the row is opened.
  await expect(dialog.locator(".history-fields")).toHaveCount(0);
  await edit.getByRole("button", { name: "Show what changed" }).click();
  await expect(edit).toContainText(
    "First draft of the pricing summary. to Second draft, with the 8% discount.",
  );

  // And the way back. Version 1 is the note as first written, reached as the
  // "before" of the edit that replaced it (D-120).
  await edit.getByRole("button", { name: "Restore version 1" }).click();
  await expect(dialog.getByRole("button", { name: "Close" })).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
  await expect(note).toContainText("First draft of the pricing summary.");
  // Restoring is an edit of its own, so the marker stays: the note was
  // edited, and the history now records three states rather than one.
  await expect(note.getByText("edited")).toBeVisible();
});

/**
 * The opportunity half of the same requirement: the case that prompted it is a
 * deal whose value moves, which used to leave no record of the figure it had.
 */
test("an opportunity's history keeps the value an edit replaced", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Revision ${suffix}`;

  await signUp(page, `revision-${suffix}@opptrail.test`, "Revision Tester");
  await createOpportunity(page, opportunity, {
    account: "Initech",
    value: "485000",
    currency: "USD",
  });
  await openTimeline(page, opportunity);

  const form = page.locator("form.opportunity-form");
  await page
    .locator("article.opportunity-card")
    .filter({ hasText: opportunity })
    .first()
    .getByRole("button", { name: "Edit" })
    .click();
  await form.getByLabel("Value").fill("250000");
  await form.getByRole("button", { name: "Save changes" }).click();
  await expect(form).toBeHidden();

  const dialog = await openHistory(page);
  const edit = dialog
    .locator("li.activity-event")
    .filter({ hasText: "changed Value on this opportunity" });
  // Restore is on the row, not inside the disclosure (3.7, D-136 finding 2):
  // it is offered before the diff is even asked for.
  await expect(
    edit.getByRole("button", { name: "Restore version 1" }),
  ).toBeVisible();
  await edit.getByRole("button", { name: "Show what changed" }).click();
  await expect(edit).toContainText("USD 485,000 to USD 250,000");

  await edit.getByRole("button", { name: "Restore version 1" }).click();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.locator(".opportunity-facts")).toContainText("USD 485,000");
});

/**
 * Milestone 3.0, completed by 3.1c: the three mechanisms read as one list.
 *
 * The point of the journey is that a reader asking "who did what when" finds
 * one screen rather than three — so this drives an event of each kind through
 * the real stack (a system entry from creating the deal, a version row from
 * editing it, an audit row from deleting an entry) and reads them back off
 * the one dialog, in order.
 */
test("the history merges what was recorded, edited and deleted", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Merged log ${suffix}`;

  await signUp(page, `activity-${suffix}@opptrail.test`, "Activity Tester");
  await createOpportunity(page, opportunity, {
    account: "Umbrella",
    value: "90000",
    currency: "USD",
  });
  await openTimeline(page, opportunity);

  await openEntryForm(page);
  await entryForm(page).getByLabel("Title").fill("Kickoff call");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  const kickoff = entry(page, "Kickoff call");
  await expect(kickoff).toBeVisible();

  // An edit to a field the timeline does not narrate: nothing but the version
  // row records this one, which is what made it invisible before 3.0.
  const form = page.locator("form.opportunity-form");
  await page
    .locator("article.opportunity-card")
    .filter({ hasText: opportunity })
    .first()
    .getByRole("button", { name: "Edit" })
    .click();
  await form.getByLabel("Value").fill("120000");
  await form.getByRole("button", { name: "Save changes" }).click();
  await expect(form).toBeHidden();

  await kickoff.getByRole("button", { name: "Delete" }).first().click();
  await expect(page.getByRole("heading", { name: "Kickoff call" })).toHaveCount(
    0,
  );

  const dialog = await openHistory(page);
  const events = dialog.locator("li.activity-event");
  await expect(events).toHaveCount(3);
  await expect(events.first()).toContainText(
    `${opportunity} was created for Umbrella.`,
  );
  await expect(events.nth(1)).toContainText(
    "changed Value on this opportunity",
  );
  await expect(events.nth(2)).toContainText("deleted the entry");
});
