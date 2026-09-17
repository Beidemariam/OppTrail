import { expect, test } from "@playwright/test";
import { entry, entryForm, openTimeline, opportunityForm, signUp } from "./helpers";

/**
 * Critical journey 3 (brief §6.3): edit a note, see the edit marker, and find
 * the previous text in the revision history.
 *
 * The first half is driven through the UI. The revision history is asserted
 * against `GET /api/notes/{id}/versions` because the frontend has no history
 * view yet — the endpoint and the `note_versions` table ship, the screen does
 * not. That gap is recorded in the Phase F review packet rather than closed
 * here: brief §4 rules out new user-facing features in this phase.
 */
test("editing a note marks it as edited and keeps the previous version", async ({ page }) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `History ${suffix}`;

  await signUp(page, `history-${suffix}@opptrail.test`, "History Tester");
  const form = opportunityForm(page);
  await form.getByLabel("Opportunity").fill(opportunity);
  await form.getByLabel("Account").fill("Cyberdyne");
  await form.getByLabel("Value").fill("15000");
  await form.getByLabel("Currency").fill("USD");
  await form.getByRole("button", { name: "Create opportunity" }).click();
  await openTimeline(page, opportunity);

  await entryForm(page).getByLabel("Title").fill("Pricing conversation");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  await expect(page.getByRole("heading", { name: "Pricing conversation" })).toBeVisible();

  const pricing = entry(page, "Pricing conversation");
  await pricing.getByPlaceholder("Add note").fill("First draft of the pricing summary.");
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

  // Revision history, over the API the page's own session is authenticated for.
  // `page.request` shares the browser context's cookies; the bare `request`
  // fixture would arrive unauthenticated.
  const timeline = await page.request.get(
    `/api/opportunities/${await opportunityId(page)}/timeline`,
  );
  expect(timeline.ok()).toBeTruthy();
  const noteId = (await timeline.json()).entries
    .flatMap((entry: { notes: { id: number; body: string }[] }) => entry.notes)
    .find((candidate: { body: string }) => candidate.body.includes("Second draft")).id;

  const versions = await page.request.get(`/api/notes/${noteId}/versions`);
  expect(versions.ok()).toBeTruthy();
  const bodies = (await versions.json()).map((version: { body: string }) => version.body);
  expect(bodies).toEqual([
    "First draft of the pricing summary.",
    "Second draft, with the 8% discount.",
  ]);
});

/** The id of the opportunity whose timeline is currently open. */
async function opportunityId(page: import("@playwright/test").Page): Promise<number> {
  const href = await page.locator(".export-actions a", { hasText: "JSON" }).getAttribute("href");
  return Number(href!.split("/")[3]);
}
