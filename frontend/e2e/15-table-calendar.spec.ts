import { expect, test } from "@playwright/test";
import {
  createOpportunity,
  expectNoAccessibilityViolations,
  openTimeline,
  signUp,
} from "./helpers";

/**
 * The third and fourth views over one dataset (milestone 2.8), walked as a
 * user: the table's columns and header sorting, and the calendar's month.
 *
 * Both are asserted through the URL as well as through the screen, because
 * that is what makes a view linkable and what a saved view stores
 * (`lib/viewState.ts`). A view that draws correctly but does not survive a
 * reload has only half shipped.
 */

function tableRow(page: import("@playwright/test").Page, name: string) {
  return page
    .locator("article.opportunity-table-row")
    .filter({ hasText: name })
    .first();
}

test("the table shows chosen columns, sorts from its headers, and survives a reload", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const bigger = `Zeta table ${suffix}`;
  const smaller = `Alpha table ${suffix}`;

  await signUp(page, `table-${suffix}@opptrail.test`, "Table Tester");
  await createOpportunity(page, bigger, { account: "Zenith", value: "90000" });
  await createOpportunity(page, smaller, { account: "Acme", value: "10000" });

  await page.getByRole("button", { name: "Table" }).click();
  await expect(tableRow(page, bigger)).toBeVisible();
  await expect(tableRow(page, bigger)).toContainText("USD 90,000");

  // A column the reader turns on is drawn, and is one they can sort by.
  await page.getByRole("button", { name: "Columns (5)" }).click();
  await page.getByRole("checkbox", { name: "Created" }).click();
  await expect(
    page.getByRole("button", { name: "Sort by Created" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Columns (6)" }).click();

  // Sorting from a header: ascending on the first click, reversed on the
  // second. Rows are addressed by position, because their order is the thing
  // under test.
  await page.getByRole("button", { name: "Sort by Value" }).click();
  await expect(
    page.locator("article.opportunity-table-row").first(),
  ).toContainText(smaller);
  await page.getByRole("button", { name: "Sort by Value" }).click();
  await expect(
    page.locator("article.opportunity-table-row").first(),
  ).toContainText(bigger);

  await expectNoAccessibilityViolations(page, "table view");

  // Columns, sort and renderer are all in the URL, so a reload lands on the
  // same table.
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Sort by Created" }),
  ).toBeVisible();
  await expect(
    page.locator("article.opportunity-table-row").first(),
  ).toContainText(bigger);
});

test("compact density is remembered across a reload", async ({ page }) => {
  const suffix = Math.random().toString(36).slice(2, 8);

  await signUp(page, `density-${suffix}@opptrail.test`, "Density Tester");
  await createOpportunity(page, `Dense ${suffix}`);

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Row density").selectOption("compact");
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");

  // Stored rather than in the URL: it is how this reader likes tables, not
  // part of the view being linked.
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
  await expect(page.getByLabel("Row density")).toHaveValue("compact");
});

test("the calendar places a deal on its close month and accounts for the rest", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const dated = `May deal ${suffix}`;
  const undated = `No date ${suffix}`;

  await signUp(page, `calendar-${suffix}@opptrail.test`, "Calendar Tester");
  // A fixed date rather than one computed from today: the month the test
  // navigates to has to be the month the deal is in, whatever day it runs on.
  await createOpportunity(page, dated, { closeDate: "2027-05-14" });
  await createOpportunity(page, undated);

  await page.goto("/?opportunities.view=calendar&opportunities.month=2027-05");
  await expect(page.getByRole("heading", { name: "May 2027" })).toBeVisible();
  await expect(page.getByRole("link", { name: dated })).toBeVisible();

  // The deal a calendar cannot place is listed rather than dropped: a view
  // that silently omits rows is how a reader concludes they have fewer deals
  // than they do (D-076).
  await expect(
    page.getByRole("heading", { name: "No close date (1)" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: undated })).toBeVisible();

  await expectNoAccessibilityViolations(page, "calendar view");

  // Walking to the next month leaves it behind, and the month is in the URL.
  await page.getByRole("button", { name: "Next month" }).click();
  await expect(page.getByRole("heading", { name: "June 2027" })).toBeVisible();
  await expect(page.getByRole("link", { name: dated })).toHaveCount(0);
  await expect(page).toHaveURL(/opportunities\.month=2027-06/);

  // And the deal is still reachable from it: a chip is the same opportunity
  // the board draws as a card.
  await page.getByRole("button", { name: "Previous month" }).click();
  await page.getByRole("link", { name: dated }).click();
  await expect(
    page.locator(".timeline-panel").getByRole("heading", { name: dated }),
  ).toBeVisible();
});

test("the calendar's second layer draws a task's due date and links back to its deal (milestone 3.0b, tasks since 4.2)", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Follow-up deal ${suffix}`;

  await signUp(page, `followup-${suffix}@opptrail.test`, "Follow-up Tester");
  await createOpportunity(page, opportunity);
  await openTimeline(page, opportunity);

  // A task rather than an entry's `follow_up_date`: milestone 4.2 migrated the
  // dates into tasks and removed the field, so this is the same layer reading a
  // different source.
  const panel = page.locator(".task-panel");
  await panel.getByRole("button", { name: "Add task" }).click();
  await panel.getByLabel("Task title").fill("Send updated pricing");
  await panel
    .getByLabel("Who this task is for")
    .selectOption({ label: "Follow-up Tester" });
  await panel.getByLabel("When this task is due").fill("2027-08-19");
  await panel.getByRole("button", { name: "Add Task" }).click();
  await expect(panel.getByText("Send updated pricing")).toBeVisible();

  await page.goto("/?opportunities.view=calendar&opportunities.month=2027-08");
  await expect(
    page.getByRole("heading", { name: "August 2027" }),
  ).toBeVisible();

  const chip = page.getByRole("link", { name: /Send updated pricing/ });
  await expect(chip).toBeVisible();
  await expect(page.locator(".followup-chip")).toContainText(opportunity);

  await expectNoAccessibilityViolations(page, "calendar view with a task due");

  // The chip links to the deal; a task migrated from an entry carries `?entry=`
  // as well, which is how it reaches the conversation that produced it.
  await chip.click();
  await expect(
    page.locator(".timeline-panel").getByRole("heading", { name: opportunity }),
  ).toBeVisible();
});
