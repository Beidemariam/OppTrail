import { expect, test } from "@playwright/test";

import {
  createOpportunity,
  entry,
  entryForm,
  expectNoAccessibilityViolations,
  openComposer,
  openTimeline,
  signUp,
} from "./helpers";

/**
 * Milestone 3.1: a real editor, storing Markdown (`docs/FEATURES.md` §4).
 *
 * This is the journey the unit suite cannot run. Everything the composer does
 * with a keystroke — the Markdown input rules that turn `- ` into a list, the
 * caret, the toolbar acting on a selection — needs a browser: jsdom accepts
 * the keys and never changes the document, because ProseMirror reads back the
 * DOM mutation a real browser makes and jsdom makes none (`app/test-editor.ts`
 * says the same thing from the other side).
 *
 * `docs/ROADMAP.md`'s acceptance criterion for Phase 3 is here in one line: "a
 * bullet list can be typed in a note".
 */
test("type a bullet list in a note, and read it back as a list", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Rich text ${suffix}`;

  await signUp(page, `rich-${suffix}@opptrail.test`, "Rich Text Tester");
  await createOpportunity(page, opportunity, { account: "Cyberdyne" });
  await openTimeline(page, opportunity);

  // An entry body is the same composer as a note's, so it is typed the same
  // way — including the input rule for a heading-free structure.
  await entryForm(page).getByLabel("Title").fill("Pricing pushback");
  const body = entryForm(page).getByLabel("Body");
  await body.click();
  await body.pressSequentially("They want **20%** off list.");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  const pushback = entry(page, "Pricing pushback");
  await expect(pushback.locator("strong")).toHaveText("20%");

  // The requirement: a bullet list, typed, in a note.
  const note = await openComposer(
    pushback,
    "Add note",
    "Add a note to this entry",
  );
  await note.click();
  await note.pressSequentially("Objections raised:\n");
  await note.pressSequentially("- price against Initech\n");
  await note.pressSequentially("security review\n");
  await note.pressSequentially("legal wants the DPA");
  // The input rule made a list of the first item, and Enter continued it: one
  // list of three, not three paragraphs starting with a dash.
  await expect(note.locator("ul li")).toHaveCount(3);
  await pushback.getByRole("button", { name: "Add Note" }).click();

  const posted = pushback.locator("section.note-block").first();
  await expect(posted.locator("ul li")).toHaveCount(3);
  await expect(posted.locator("ul li").first()).toHaveText(
    "price against Initech",
  );

  // What was stored is Markdown, which is the whole reason this needed no
  // migration: the editor reopens the note as the same list.
  await posted.getByRole("button", { name: "Edit" }).click();
  const editing = posted.getByLabel("Edit this note");
  await expect(editing.locator("ul li")).toHaveCount(3);

  // The toolbar says what the cursor is inside, and acts on it: with the
  // cursor in a bullet, Bullets is pressed, and Checklist turns that list into
  // one.
  await editing.locator("ul li").first().click();
  await expect(posted.getByRole("button", { name: "Bullets" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const checklist = posted.getByRole("button", { name: "Checklist" });
  await checklist.click();
  await expect(checklist).toHaveAttribute("aria-pressed", "true");
  await posted.getByRole("button", { name: "Save" }).click();

  // And it reads back as a box: the item the cursor was in, unticked because
  // that is how it was saved, with the other two still bullets — a list toggle
  // takes the item it was asked about, not the whole list.
  const boxes = posted.locator("input[type=checkbox]");
  await expect(boxes).toHaveCount(1);
  await expect(boxes.first()).not.toBeChecked();
  await expect(posted.locator("ul li")).toHaveCount(3);

  await expectNoAccessibilityViolations(page, "a timeline with rich content");
});
