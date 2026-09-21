import { expect, test } from "@playwright/test";
import {
  card,
  createOpportunity,
  expectNoAccessibilityViolations,
  openTimeline,
  signUp,
} from "./helpers";

/**
 * Critical journey 8 (brief §6.3): board view stage drag writes a system
 * entry. Milestone 2.7 is where the board can be dragged, so it lands here,
 * together with the list view over the same filters.
 *
 * The drag is a real pointer drag rather than a synthesized `drop` event:
 * what is being asserted is that a card can be picked up and carried to
 * another column, which is exactly the part a dispatched event would skip.
 */

function column(page: import("@playwright/test").Page, stage: string) {
  return page
    .locator(".stage-column")
    .filter({ has: page.getByRole("heading", { name: stage, exact: true }) });
}

test("dragging a card to another stage column logs a system entry", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Drag ${suffix}`;

  await signUp(page, `drag-${suffix}@opptrail.test`, "Drag Tester");
  await createOpportunity(page, opportunity, {
    account: "Umbrella",
    value: "64000",
    stage: "Prospecting",
  });

  await expect(
    column(page, "Prospecting").getByRole("link", { name: opportunity }),
  ).toBeVisible();
  await card(page, opportunity).dragTo(column(page, "Proposal"));

  // The card is in its new column, and the stage change is on the timeline as
  // an entry nobody can edit.
  await expect(
    column(page, "Proposal").getByRole("link", { name: opportunity }),
  ).toBeVisible();
  await expect(
    column(page, "Prospecting").getByRole("link", { name: opportunity }),
  ).toHaveCount(0);

  await openTimeline(page, opportunity);
  const systemEntry = page
    .locator("article.timeline-entry")
    .filter({ hasText: "Stage changed to Proposal" });
  await expect(systemEntry).toBeVisible();
  await expect(systemEntry.getByText("System")).toBeVisible();
  await expect(systemEntry.getByRole("button", { name: "Edit" })).toHaveCount(
    0,
  );
});

test("the same move is available without a mouse, and the list view shows it", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Keyboard move ${suffix}`;

  await signUp(page, `move-${suffix}@opptrail.test`, "Move Tester");
  await createOpportunity(page, opportunity, {
    account: "Tyrell",
    stage: "Qualification",
  });

  // `docs/DESIGN-SYSTEM.md`: drag needs a keyboard alternative, or the board
  // is unusable without a mouse.
  await card(page, opportunity)
    .getByLabel(`Move ${opportunity} to stage`)
    .selectOption("Negotiation");
  await expect(
    column(page, "Negotiation").getByRole("link", { name: opportunity }),
  ).toBeVisible();

  // The list is the same data, one renderer along, and it says which stage
  // each row is in.
  await page.getByRole("button", { name: "List" }).click();
  await expect(page.locator(".stage-board")).toHaveCount(0);
  const row = page.locator("article.opportunity-row").filter({
    hasText: opportunity,
  });
  await expect(row.getByLabel(`Move ${opportunity} to stage`)).toHaveValue(
    "Negotiation",
  );
  await expectNoAccessibilityViolations(page, "list view");

  // And it survives a reload, because the view is part of the URL.
  await page.reload();
  await expect(
    page.locator("article.opportunity-row").filter({ hasText: opportunity }),
  ).toBeVisible();
});
