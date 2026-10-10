import { expect, test } from "@playwright/test";

import {
  NORTHWIND,
  createOpportunity,
  openEntryForm,
  openTimeline,
  signUp,
} from "./helpers";

/**
 * Custom fields (milestone 6.1, ADR 0006, `docs/FEATURES.md` §3).
 *
 * The roadmap's acceptance criterion is one sentence: "a new select field
 * appears as a table column, a filter, and on the entry form." This walks
 * exactly that, in a real browser against the real API, because the three
 * places are three different screens reading one definition list and the
 * component tests cannot see them agree.
 */
test("a new select field becomes a column, a filter and a form input", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const label = `Region ${suffix}`;
  const opportunity = `Fields ${suffix}`;

  await signUp(page, `fields-${suffix}@opptrail.test`, "Field Definer");

  // --- define it ---
  await page.getByRole("button", { name: "Fields" }).click();
  const dialog = page.getByRole("dialog", { name: "Custom fields" });
  await dialog.getByLabel("Label").fill(label);
  await dialog.getByLabel("Type").selectOption("select");
  await dialog.getByLabel("Options, separated by commas").fill("EMEA, APAC");
  await dialog.getByRole("button", { name: "Add field" }).click();
  await expect(
    dialog.getByRole("listitem").filter({ hasText: label }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();

  // --- set a value on a deal ---
  await createOpportunity(page, opportunity, { account: "Initech" });
  await page.getByRole("button", { name: "New opportunity" }).click();
  const form = page.getByRole("dialog", { name: "Opportunity" });
  await form.getByLabel("Opportunity").fill(`${opportunity} APAC`);
  await form.getByLabel("Account").fill("Initech");
  await form.getByLabel(label).selectOption("APAC");
  await form.getByRole("button", { name: "Create opportunity" }).click();

  // --- a filter ---
  await page
    .getByRole("combobox", { name: `Filter by ${label}` })
    .selectOption("APAC");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(
    page.getByRole("link", { name: `${opportunity} APAC` }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: opportunity, exact: true }),
  ).toHaveCount(0);
  // Linkable, like every other filter (milestone 2.2).
  await expect(page).toHaveURL(/opportunities\.custom=/);

  // --- a table column ---
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByRole("button", { name: /^Columns/ }).click();
  await page
    .getByRole("group", { name: "Columns shown in the table" })
    .getByLabel(label)
    // `.click()` rather than `.check()`: ticking a column re-renders the
    // panel, and Playwright's `check` re-reads the element it just clicked to
    // confirm the state changed -- the trap `e2e/24-tasks.spec.ts` already
    // records for a checkbox whose row moves under it.
    .click();
  await expect(
    page
      .getByRole("region", { name: "Opportunities" })
      .getByText("APAC")
      .first(),
  ).toBeVisible();
});

test("an entry field appears on the entry form and is kept", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const label = `Sentiment ${suffix}`;

  await signUp(page, `entryfields-${suffix}@opptrail.test`, "Entry Definer");
  await page.getByRole("button", { name: "Fields" }).click();
  const dialog = page.getByRole("dialog", { name: "Custom fields" });
  await dialog.getByLabel("These fields are on").selectOption("entry");
  await dialog.getByLabel("Label").fill(label);
  await dialog.getByLabel("Type").selectOption("select");
  await dialog.getByLabel("Options, separated by commas").fill("Warm, Cold");
  await dialog.getByRole("button", { name: "Add field" }).click();
  await expect(
    dialog.getByRole("listitem").filter({ hasText: label }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();

  const opportunity = `Entry fields ${suffix}`;
  await createOpportunity(page, opportunity, { account: "Initech" });
  await openTimeline(page, opportunity);

  await openEntryForm(page);
  await page.getByLabel("Title").fill("Pricing call");
  await page.getByLabel(label).selectOption("Warm");
  await page.getByRole("button", { name: "Add Entry" }).click();

  // The value survives the round trip, which is what makes it a field rather
  // than a form control: it is read back from the entry the API returns.
  const entry = page
    .locator(".timeline-entry")
    .filter({ hasText: "Pricing call" });
  await expect(entry).toBeVisible();
  await entry.getByRole("button", { name: "Edit" }).click();
  await expect(page.getByLabel(label)).toHaveValue("Warm");
});

test("archiving a field hides it everywhere without losing the value", async ({
  page,
}) => {
  // ADR 0006's load-bearing property, from the reader's side: the column and
  // the filter disappear, and restoring the definition brings the value back.
  const suffix = Math.random().toString(36).slice(2, 8);
  const label = `Tier ${suffix}`;
  const opportunity = `Archive ${suffix}`;

  await signUp(page, `archive-${suffix}@opptrail.test`, "Archiver");
  await page.getByRole("button", { name: "Fields" }).click();
  const dialog = page.getByRole("dialog", { name: "Custom fields" });
  await dialog.getByLabel("Label").fill(label);
  await dialog.getByLabel("Type").selectOption("select");
  await dialog.getByLabel("Options, separated by commas").fill("Gold, Silver");
  await dialog.getByRole("button", { name: "Add field" }).click();
  await expect(
    dialog.getByRole("listitem").filter({ hasText: label }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();

  await createOpportunity(page, opportunity, { account: "Initech" });
  await page.getByRole("button", { name: "New opportunity" }).click();
  const form = page.getByRole("dialog", { name: "Opportunity" });
  await form.getByLabel("Opportunity").fill(`${opportunity} Gold`);
  await form.getByLabel("Account").fill("Initech");
  await form.getByLabel(label).selectOption("Gold");
  await form.getByRole("button", { name: "Create opportunity" }).click();
  await expect(
    page.getByRole("combobox", { name: `Filter by ${label}` }),
  ).toBeVisible();

  // Archive, not delete: nothing here offers to destroy a stored value.
  await page.getByRole("button", { name: "Fields" }).click();
  const row = dialog.getByRole("listitem").filter({ hasText: label });
  await expect(row.getByRole("button", { name: "Delete" })).toHaveCount(0);
  await row.getByRole("button", { name: "Archive" }).click();
  await expect(row.getByRole("button", { name: "Restore" })).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();

  await expect(
    page.getByRole("combobox", { name: `Filter by ${label}` }),
  ).toHaveCount(0);

  // And back: the value was never rewritten, so it reappears.
  await page.getByRole("button", { name: "Fields" }).click();
  await dialog
    .getByRole("listitem")
    .filter({ hasText: label })
    .getByRole("button", { name: "Restore" })
    .click();
  await dialog.getByRole("button", { name: "Close" }).click();
  await page
    .getByRole("combobox", { name: `Filter by ${label}` })
    .selectOption("Gold");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(
    page.getByRole("link", { name: `${opportunity} Gold` }),
  ).toBeVisible();
});
