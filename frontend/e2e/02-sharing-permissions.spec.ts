import { expect, test } from "@playwright/test";
import {
  card,
  entry,
  entryForm,
  openTimeline,
  createOpportunity,
  signIn,
  signOut,
  signUp,
} from "./helpers";

/**
 * Critical journey 2 (brief §6.3): share as viewer and verify read-only, then
 * upgrade to editor and verify the editor can add and edit their own note but
 * still cannot edit a comment — comments are immutable to everyone (§2.2).
 */
test("viewer is read-only, editor can write, comments stay immutable", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const ownerEmail = `share-owner-${suffix}@opptrail.test`;
  const guestEmail = `share-guest-${suffix}@opptrail.test`;
  const opportunity = `Shared ${suffix}`;

  await signUp(page, guestEmail, "Guest Tester");
  await signOut(page);

  await signUp(page, ownerEmail, "Owner Tester");
  await createOpportunity(page, opportunity, {
    account: "Stark Industries",
    value: "30000",
    currency: "USD",
  });
  await openTimeline(page, opportunity);

  await entryForm(page).getByLabel("Title").fill("Kickoff");
  await entryForm(page).getByLabel("Body").fill("First conversation.");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  await expect(page.getByRole("heading", { name: "Kickoff" })).toBeVisible();

  const kickoff = entry(page, "Kickoff");
  await kickoff.getByPlaceholder("Add note").fill("Owner's note");
  await kickoff.getByRole("button", { name: "Add Note" }).click();
  await expect(page.getByText("Owner's note")).toBeVisible();

  await page.getByPlaceholder("Colleague email").fill(guestEmail);
  await page.locator("form.share-form select").selectOption("viewer");
  await page.getByRole("button", { name: "Share", exact: true }).click();
  await expect(
    page.locator(".share-row").filter({ hasText: guestEmail }),
  ).toBeVisible();
  await signOut(page);

  // --- As a viewer: everything readable, nothing writable ---------------
  await signIn(page, guestEmail);
  await expect(card(page, opportunity)).toBeVisible();
  await expect(card(page, opportunity).getByText("viewer")).toBeVisible();
  await expect(
    card(page, opportunity).getByRole("button", { name: "Delete" }),
  ).toHaveCount(0);

  await openTimeline(page, opportunity);
  await expect(page.getByText("Owner's note")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add Entry" })).toHaveCount(0);
  await expect(page.getByPlaceholder("Add note")).toHaveCount(0);
  await expect(page.getByPlaceholder("Add comment")).toHaveCount(0);
  // Sharing and the audit log are the owner's alone.
  await expect(page.locator(".sharing-panel")).toHaveCount(0);
  await signOut(page);

  // --- Upgrade to editor ------------------------------------------------
  await signIn(page, ownerEmail);
  await openTimeline(page, opportunity);
  await page
    .locator(".share-row")
    .filter({ hasText: guestEmail })
    .locator("select")
    .selectOption("editor");
  await expect(
    page
      .locator(".share-row")
      .filter({ hasText: guestEmail })
      .locator("select"),
  ).toHaveValue("editor");
  await signOut(page);

  // --- As an editor: can add, can change only their own ------------------
  await signIn(page, guestEmail);
  await openTimeline(page, opportunity);

  const editorEntry = entry(page, "Kickoff");
  await editorEntry.getByPlaceholder("Add note").fill("Editor's own note");
  await editorEntry.getByRole("button", { name: "Add Note" }).click();
  const editorNote = page
    .locator("section.note-block")
    .filter({ hasText: "Editor's own note" });
  await expect(editorNote).toBeVisible();
  await expect(editorNote.getByRole("button", { name: "Edit" })).toBeVisible();

  // The owner's note is not the editor's to change (D-005).
  const ownersNote = page
    .locator("section.note-block")
    .filter({ hasText: "Owner's note" });
  await expect(ownersNote.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await expect(ownersNote.getByRole("button", { name: "Delete" })).toHaveCount(
    0,
  );

  await editorNote.getByPlaceholder("Add comment").fill("Editor's comment");
  await editorNote.getByRole("button", { name: "Post" }).click();
  const comment = editorNote
    .locator(".comment-row")
    .filter({ hasText: "Editor's comment" });
  await expect(comment).toBeVisible();

  // A comment can be removed by its author but never edited, by anyone.
  await expect(comment.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await expect(comment.getByRole("button", { name: "Delete" })).toBeVisible();
});

/**
 * The UI half of "absence of access returns 404, not 403" (`CLAUDE.md`,
 * Permissions): an opportunity nobody shared should not exist as far as an
 * unrelated user's screen is concerned, not on the dashboard and not at the
 * URL a colleague could open.
 */
test("an unrelated user sees no trace of the opportunity, on the dashboard or at its URL", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const ownerEmail = `trace-owner-${suffix}@opptrail.test`;
  const strangerEmail = `trace-stranger-${suffix}@opptrail.test`;
  const opportunity = `Private ${suffix}`;

  await signUp(page, strangerEmail, "Unrelated Stranger");
  await signOut(page);

  await signUp(page, ownerEmail, "Private Owner");
  await createOpportunity(page, opportunity, { account: "Wayne Enterprises" });
  await openTimeline(page, opportunity);
  const opportunityUrl = page.url();
  await signOut(page);

  await signIn(page, strangerEmail);
  await expect(
    page.getByRole("heading", { name: "Opportunities" }),
  ).toBeVisible();
  await expect(card(page, opportunity)).toHaveCount(0);

  // Not shared with this reader, so the same URL the owner used answers "not
  // available" rather than leaking the name or any timeline content.
  await page.goto(opportunityUrl);
  await expect(
    page.getByRole("heading", { name: "This opportunity is not available." }),
  ).toBeVisible();
  await expect(page.getByText(opportunity)).toHaveCount(0);
});
