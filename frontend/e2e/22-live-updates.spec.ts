import { expect, test } from "@playwright/test";

import {
  ALEX,
  BLAIR,
  NORTHWIND,
  addNote,
  entry,
  entryForm,
  openEntryForm,
  openTimeline,
  signIn,
} from "./helpers";

/**
 * Milestone 3.4, ADR 0003: two people on one deal see each other.
 *
 * This is the one suite that needs two real browser contexts. Everything
 * below it -- the in-process broker, the key mapping, the 409 -- is covered by
 * `backend/tests/test_events.py` and `frontend/app/LiveUpdates.test.tsx`
 * against fakes; what only a browser can show is that the transport is really
 * server-sent events, that the reader's `EventSource` really reconnects and
 * really refetches, and that neither person pressed reload.
 *
 * It runs on the seeded pairing rather than a fresh deal: Alex owns Northwind
 * and Blair edits it, which is the relationship both halves of the ADR are
 * about.
 */

test("a colleague's entry appears without a reload", async ({
  page,
  browser,
}) => {
  const title = `Live entry ${Math.random().toString(36).slice(2, 8)}`;

  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);
  await expect(page.getByRole("heading", { name: title })).toBeHidden();

  const second = await browser.newContext();
  const blair = await second.newPage();
  try {
    await signIn(blair, BLAIR);
    await openTimeline(blair, NORTHWIND);
    await openEntryForm(blair);
    await entryForm(blair).getByLabel("Title").fill(title);
    await entryForm(blair).getByRole("button", { name: "Add Entry" }).click();
    await expect(blair.getByRole("heading", { name: title })).toBeVisible();

    // Alex's page has not been touched since the assertion above. If the
    // stream were not open, this would only pass on a reload.
    await expect(
      page.locator(".timeline-panel").getByRole("heading", { name: title }),
    ).toBeVisible();
  } finally {
    await second.close();
  }
});

test("a note saved against a copy somebody else moved is refused", async ({
  page,
  browser,
}) => {
  const title = `Conflict ${Math.random().toString(36).slice(2, 8)}`;

  // Blair writes the entry and the note, so both people may edit it: changing
  // an existing item is the author-or-owner rule (D-005), and Alex is the
  // owner. A fresh entry, so each side's note is the first one under a title
  // that is unique to this run -- addressing it by the body would stop
  // matching the moment the body is what changes.
  const second = await browser.newContext();
  const blair = await second.newPage();
  try {
    await signIn(blair, BLAIR);
    await openTimeline(blair, NORTHWIND);
    await openEntryForm(blair);
    await entryForm(blair).getByLabel("Title").fill(title);
    await entryForm(blair).getByRole("button", { name: "Add Entry" }).click();
    await expect(blair.getByRole("heading", { name: title })).toBeVisible();
    await addNote(entry(blair, title), "The first draft.");

    const blairNote = entry(blair, title).locator("section.note-block").first();
    await blairNote.getByRole("button", { name: "Edit" }).click();

    await signIn(page, ALEX);
    await openTimeline(page, NORTHWIND);
    const alexNote = entry(page, title).locator("section.note-block").first();
    await alexNote.getByRole("button", { name: "Edit" }).click();
    await alexNote.getByLabel("Edit this note").fill("Alex got here first.");
    await alexNote.getByRole("button", { name: "Save" }).click();
    await expect(alexNote).toContainText("Alex got here first.");

    // Blair's editor is still open on the copy that has just been replaced --
    // the live stream refetched the note underneath it, and the guard compares
    // against what the editor was opened with rather than what is on screen
    // now (`app/NoteBlock.tsx`).
    await blairNote.getByLabel("Edit this note").fill("Blair's version");
    await blairNote.getByRole("button", { name: "Save" }).click();

    await expect(blairNote).toContainText("Somebody else saved this note");
    await blairNote.getByRole("button", { name: "Discard my edit" }).click();
    await expect(blairNote).toContainText("Alex got here first.");
  } finally {
    await second.close();
  }
});
