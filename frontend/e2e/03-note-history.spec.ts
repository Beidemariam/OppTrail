import { expect, test } from "@playwright/test";
import {
  entry,
  entryForm,
  openTimeline,
  createOpportunity,
  signUp,
} from "./helpers";

/**
 * Critical journey 3 (brief §6.3): edit a note, see the edit marker, and find
 * the previous text in the revision history — plus the other two histories
 * milestone 2.10 added beside it.
 *
 * Driven entirely through the UI since 2.10. It used to read the versions over
 * `GET /api/v2/notes/{id}/versions` because the frontend had no history view:
 * the table and the endpoint shipped in Phase F, the screen did not. It does
 * now, for all three editable things, and the History button is owner-only
 * (D-096) — the signed-up user here owns what they create.
 */
test("editing a note marks it as edited and keeps the previous version", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `History ${suffix}`;

  await signUp(page, `history-${suffix}@opptrail.test`, "History Tester");
  await createOpportunity(page, opportunity, {
    account: "Cyberdyne",
    value: "15000",
    currency: "USD",
  });
  await openTimeline(page, opportunity);

  await entryForm(page).getByLabel("Title").fill("Pricing conversation");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  await expect(
    page.getByRole("heading", { name: "Pricing conversation" }),
  ).toBeVisible();

  const pricing = entry(page, "Pricing conversation");
  await pricing
    .getByPlaceholder("Add note")
    .fill("First draft of the pricing summary.");
  await pricing.getByRole("button", { name: "Add Note" }).click();

  // Addressed by position, not by its text: the text is about to change, and a
  // text filter would stop matching the moment the textarea is retyped.
  const note = pricing.locator("section.note-block").first();
  await expect(note).toContainText("First draft of the pricing summary.");
  await expect(note.getByText("edited")).toHaveCount(0);

  await note.getByRole("button", { name: "Edit" }).click();
  await note.locator("textarea").fill("Second draft, with the 8% discount.");
  await note.getByRole("button", { name: "Save" }).click();

  await expect(note).toContainText("Second draft, with the 8% discount.");
  await expect(note.getByText("edited")).toBeVisible();

  // The revision history, on the screen milestone 2.10 gave it.
  await note.getByRole("button", { name: "History" }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "History of this note" }),
  ).toBeVisible();
  const versions = dialog.locator("li.history-version");
  await expect(versions).toHaveCount(2);
  await expect(versions.first()).toContainText(
    "First draft of the pricing summary.",
  );
  await expect(versions.nth(1)).toContainText(
    "First draft of the pricing summary. to Second draft, with the 8% discount.",
  );
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
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

  await page
    .locator(".timeline-heading")
    .getByRole("button", { name: "History" })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: `History of ${opportunity}` }),
  ).toBeVisible();
  const versions = dialog.locator("li.history-version");
  await expect(versions).toHaveCount(2);
  await expect(versions.first()).toContainText("USD 485,000");
  await expect(versions.nth(1)).toContainText("USD 485,000 to USD 250,000");
});
