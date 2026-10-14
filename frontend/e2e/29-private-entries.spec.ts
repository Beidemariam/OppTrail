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
test("an entry kept private is sealed for a colleague and whole for its author", async ({
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

    // Blair is shared on this deal, and meets a sealed card: the entry is
    // there, in its place, carrying nothing.
    await expect(blair.getByText(title)).toHaveCount(0);
    await expect(blair.getByText("The part nobody else sees.")).toHaveCount(0);
    await expect(
      blair.getByText(/kept this entry to themselves/).first(),
    ).toBeVisible();
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

  const notebook = page.locator("section.private-note-panel");
  await notebook
    .getByRole("button", { name: /Keep a note on this deal, just for you/ })
    .click();
  await notebook.getByLabel("My private notes on this deal").fill(held);
  await notebook.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(held)).toBeVisible();

  const second = await browser.newContext();
  const blair = await second.newPage();
  try {
    await signIn(blair, BLAIR);
    await openTimeline(blair, NORTHWIND);

    // Blair's own notebook is empty, and the search that spans every deal
    // they can read finds nothing of Alex's.
    await expect(
      blair.locator("section.private-note-panel").getByRole("button", {
        name: /Keep a note on this deal, just for you/,
      }),
    ).toBeVisible();
    await blair.goto(`/search?q=${held.split(" ")[0]}`);
    await expect(blair.getByText(held)).toHaveCount(0);
  } finally {
    await second.close();
  }
});
