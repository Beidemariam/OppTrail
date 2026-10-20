import { expect, test } from "@playwright/test";

import {
  ALEX,
  BLAIR,
  NORTHWIND,
  entry,
  openPrivateEntryForm,
  openTimeline,
  signIn,
} from "./helpers";

/**
 * Keeping something to yourself on a shared deal (milestone R.1b).
 *
 * The journey the unit tests cannot make: two people, one deal, one browser
 * each, and the question of what the second one sees.
 */
test("an entry kept private is invisible to a colleague and whole for its author", async ({
  page,
  browser,
}) => {
  const title = `Kept back ${Math.random().toString(36).slice(2, 8)}`;
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  const form = await openPrivateEntryForm(page);
  await form.getByLabel("Title").fill(title);
  await form.getByLabel("Body").fill("The part nobody else sees.");
  await form.getByRole("button", { name: "Add Entry" }).click();

  // Its author reads it whole, marked.
  await expect(entry(page, title)).toBeVisible();
  await expect(
    entry(page, title).getByRole("button", { name: "Reveal" }),
  ).toBeVisible();

  const second = await browser.newContext();
  const blair = await second.newPage();
  try {
    await signIn(blair, BLAIR);
    await openTimeline(blair, NORTHWIND);

    // Blair is shared on this deal and meets nothing at all (R.1c, D-209):
    // not the words, and not a card saying somebody kept something back. The
    // timeline has loaded — the deal's own creation entry is on it — so this
    // is an absence rather than a page that has not arrived.
    await expect(blair.locator("article.timeline-entry").first()).toBeVisible();
    await expect(blair.getByText(title)).toHaveCount(0);
    await expect(blair.getByText("The part nobody else sees.")).toHaveCount(0);
    await expect(blair.getByText(/kept this entry to themselves/)).toHaveCount(
      0,
    );
  } finally {
    await second.close();
  }
});

test("revealing it afterwards gives a colleague the whole entry", async ({
  page,
  browser,
}) => {
  const title = `Revealed ${Math.random().toString(36).slice(2, 8)}`;
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  const form = await openPrivateEntryForm(page);
  await form.getByLabel("Title").fill(title);
  await form.getByRole("button", { name: "Add Entry" }).click();
  await expect(entry(page, title)).toBeVisible();

  await entry(page, title).getByRole("button", { name: "Reveal" }).click();
  await expect(
    entry(page, title).getByRole("button", { name: "Keep private" }),
  ).toBeVisible();

  const second = await browser.newContext();
  const blair = await second.newPage();
  try {
    await signIn(blair, BLAIR);
    await openTimeline(blair, NORTHWIND);
    await expect(blair.getByText(title)).toBeVisible();
  } finally {
    await second.close();
  }
});

test("a notebook on a deal is one person's own", async ({ page, browser }) => {
  const held = `Procurement ${Math.random().toString(36).slice(2, 8)}`;
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  // Either trigger opens the editor, and which one is showing depends on
  // whether this reader already has a notebook here: the demo seed writes one
  // for Alex on Northwind (R.7), which is what made this test wait thirty
  // seconds for an empty-state button that was never going to appear. The
  // test is about who may read a notebook, not about which state it opens in.
  const notebook = page.locator("section.private-note-panel");
  await notebook
    .getByRole("button", {
      name: /Keep a note on this deal, just for you|Edit my notes/,
    })
    .click();
  await notebook.getByLabel("My private notes on this deal").fill(held);
  await notebook.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(held)).toBeVisible();

  const second = await browser.newContext();
  const blair = await second.newPage();
  try {
    await signIn(blair, BLAIR);
    await openTimeline(blair, NORTHWIND);

    // Blair's own notebook is empty — the seed writes one for Alex only — and
    // the search that spans every deal they can read finds nothing of Alex's.
    await expect(
      blair.locator("section.private-note-panel").getByRole("button", {
        name: /Keep a note on this deal, just for you/,
      }),
    ).toBeVisible();
    await expect(blair.locator("section.private-note-panel")).not.toContainText(
      held,
    );
    await blair.goto(`/search?q=${held.split(" ")[0]}`);
    await expect(blair.getByText(held)).toHaveCount(0);
  } finally {
    await second.close();
  }
});
