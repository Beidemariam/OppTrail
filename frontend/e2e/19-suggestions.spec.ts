import { expect, test } from "@playwright/test";

import {
  ALEX,
  BLAIR,
  NORTHWIND,
  entry,
  entryForm,
  openEntryForm,
  expectNoAccessibilityViolations,
  openComposer,
  openTimeline,
  signIn,
} from "./helpers";

/**
 * Milestone 3.2: the three typed triggers, in a real browser.
 *
 * The unit suite drives the popup by pasting (`app/Suggestions.test.tsx`,
 * **D-113**), which covers what happens once a trigger has opened. What it
 * cannot cover is the typing itself — a suggestion is a reply to a keystroke,
 * and ProseMirror only sees a keystroke where a browser makes the DOM mutation
 * it reads back. So this is the journey for `@`, `/` and `#` as a person
 * performs them, and `docs/ROADMAP.md`'s "@mention autocompletes and notifies"
 * is the first half of it.
 */
test("the @ trigger completes a colleague's address instead of making it be remembered", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  await openEntryForm(page);
  const body = entryForm(page).getByLabel("Body");
  await body.click();
  // Three letters of a name, which is all requirement 13 was ever missing: the
  // address is what the notification is delivered by, and nobody types one
  // from memory.
  await body.pressSequentially("Handing over to @bla");

  const people = page.getByRole("listbox", { name: "People" });
  await expect(people).toBeVisible();
  await expect(people.getByRole("option")).toHaveCount(1);
  await expect(people.getByRole("option")).toContainText(BLAIR);
  // The caret is still in the sentence: the menu is pointed at, not focused.
  const optionId = await people.getByRole("option").first().getAttribute("id");
  expect(optionId).toBeTruthy();
  await expect(body).toHaveAttribute("aria-activedescendant", optionId ?? "");

  await expectNoAccessibilityViolations(page, "a composer with its menu open");

  await body.press("Enter");
  await expect(people).toBeHidden();
  await expect(body).toContainText(`Handing over to @${BLAIR}`);

  // And it is a mention, not decoration: posting it notifies Blair, which is
  // the same delivery `e2e/04-mentions.spec.ts` proves from a typed address.
  await entryForm(page).getByLabel("Title").fill("Handover to Blair");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  const handover = entry(page, "Handover to Blair");
  await expect(handover).toContainText(`@${BLAIR}`);
});

test("the / trigger starts a block, including the ones no button offers", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  await openEntryForm(page);
  const body = entryForm(page).getByLabel("Body");
  await body.click();
  await body.pressSequentially("/quo");

  const blocks = page.getByRole("listbox", { name: "Blocks" });
  await expect(blocks.getByRole("option")).toHaveText(["Quote> then space"]);
  await body.press("Enter");
  // The typed request goes with the answer: what was wanted is the block.
  await expect(body.locator("blockquote")).toBeVisible();
  await body.pressSequentially("They want it in writing.");
  await expect(body.locator("blockquote")).toHaveText(
    "They want it in writing.",
  );

  // A code block has no toolbar button and no obvious shortcut, which is the
  // discoverability a slash menu adds (D-111). Arrow keys pick it.
  await body.press("Enter");
  await body.press("Enter");
  await body.pressSequentially("/co");
  await expect(blocks.getByRole("option").first()).toContainText("Code block");
  await body.press("Enter");
  await expect(body.locator("pre")).toBeVisible();
});

test("the # trigger links to another entry, and the link lands on it", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  const demo = entry(page, "Product demo for the operations team");
  const note = await openComposer(demo, "Add note", "Add a note to this entry");
  await note.click();
  await note.pressSequentially("Same objection as #procure");

  const entries = page.getByRole("listbox", { name: "Entries" });
  await expect(entries.getByRole("option")).toHaveCount(1);
  await expect(entries.getByRole("option")).toContainText(
    "Procurement pushed back on price",
  );
  await note.press("Enter");
  await expect(entries).toBeHidden();

  await demo.getByRole("button", { name: "Add Note" }).click();
  const link = demo.getByRole("link", {
    name: "Procurement pushed back on price",
  });
  await expect(link).toBeVisible();

  // Following it stays in the app — no reload — and marks the entry it named,
  // which is what tells the reader which of nine cards the note meant (D-124).
  await link.click();
  await expect(page).toHaveURL(/\?entry=\d+$/);
  const linked = page.locator(".timeline-entry.is-linked");
  await expect(linked).toHaveCount(1);
  await expect(linked).toContainText("Procurement pushed back on price");
});
