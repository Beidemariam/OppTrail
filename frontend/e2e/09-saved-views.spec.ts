import { expect, test, type Page } from "@playwright/test";
import {
  ALEX,
  BLAIR,
  NORTHWIND,
  expectNoAccessibilityViolations,
  openTimeline,
  signIn,
  signUp,
} from "./helpers";

/**
 * Milestone 2.2's acceptance lines (`docs/ROADMAP.md` Phase 2): "a saved view
 * survives reload and is shareable by URL", and the timeline's reading order
 * (D-051), which is the same model applied to one opportunity's entries.
 *
 * The two states share one query string — the board stays mounted beside the
 * open timeline (D-054) — so each one's parameters are namespaced by the
 * entity it belongs to (`lib/viewState.ts`, D-059). The URLs asserted here
 * are that contract as a user meets it: what they can copy out of the address
 * bar and send to a colleague.
 */

const LATE_STAGE_VIEW = "Late-stage pipeline";

function cards(page: Page) {
  return page.locator("article.opportunity-card");
}

function entries(page: Page) {
  return page.locator(".timeline-list article.timeline-entry");
}

/**
 * Applies a saved view by name.
 *
 * By value rather than by label: since milestone 2.13 an option reads
 * "<name> - shared by <creator>", so the name alone is no longer the option's
 * label -- which is the point of the change.
 */
async function applySavedView(page: Page, name: string) {
  const menu = page.getByLabel("Saved opportunity views");
  const value = await menu
    .locator("option", { hasText: name })
    .getAttribute("value");
  await menu.selectOption(value);
}

test("a board filter is in the URL and survives a reload", async ({ page }) => {
  await signIn(page, ALEX);
  await expect(cards(page)).toHaveCount(5);

  await page.getByLabel("Filter by stage").selectOption("Negotiation");
  await page.getByRole("button", { name: "Apply" }).click();

  await expect(cards(page)).toHaveCount(1);
  await expect(cards(page)).toContainText(NORTHWIND);
  await expect(page).toHaveURL(/opportunities\.stage=Negotiation/);

  await page.reload();
  await expect(cards(page)).toHaveCount(1);
  await expect(page.getByLabel("Filter by stage")).toHaveValue("Negotiation");

  await expectNoAccessibilityViolations(
    page,
    "filtered board with saved views",
  );
});

test("a saved view is applied from the menu and is shareable by URL", async ({
  page,
}) => {
  await signIn(page, ALEX);

  await applySavedView(page, LATE_STAGE_VIEW);

  await expect(cards(page)).toHaveCount(1);
  await expect(cards(page)).toContainText(NORTHWIND);

  // Applying a view writes it into the URL, which is the whole mechanism
  // behind "shareable": there is no second thing to send.
  const shared = page.url();
  expect(shared).toContain("opportunities.stage=Negotiation");
  expect(shared).toContain("opportunities.sortField=value");

  await page.goto("/");
  await expect(cards(page)).toHaveCount(5);

  await page.goto(shared);
  await expect(cards(page)).toHaveCount(1);
  await expect(page.getByLabel("Filter by stage")).toHaveValue("Negotiation");
  await expect(page.getByLabel("Sort by")).toHaveValue("value");
});

test("a shared view reaches a colleague; a private one does not", async ({
  page,
}) => {
  // Seeded by `backend/tools/seed.py`: Alex's board view is shared, Blair's is
  // not, so Blair sees both and Alex sees only their own.
  await signIn(page, BLAIR);
  const menu = page.getByLabel("Saved opportunity views");
  await expect(menu.locator("option")).toContainText([
    "Apply a saved view...",
    "Blair's proposals",
    LATE_STAGE_VIEW,
  ]);

  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, ALEX);
  await expect(page.getByLabel("Saved opportunity views")).not.toContainText(
    "Blair's proposals",
  );
});

test("the timeline can be read newest-first, and that reading is linkable", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  // Newest-first is the default (3.1a, D-115): the oldest entry starts at
  // the bottom of the list with no control touched.
  const oldest = "Intro call with the VP of Operations";
  await expect(entries(page).last()).toContainText(oldest);

  await page
    .getByLabel("Timeline reading order")
    .selectOption({ label: "Oldest first" });
  await page.getByRole("button", { name: "Filter" }).click();

  await expect(entries(page).first()).toContainText(oldest);
  await expect(page).toHaveURL(/timeline\.order=asc/);

  // The order survives a reload, and the board's own filter is still beside it
  // in the same query string rather than having replaced it.
  await page.getByLabel("Filter by stage").selectOption("Negotiation");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/timeline\.order=asc/);

  await page.reload();
  await expect(entries(page).first()).toContainText(oldest);
  await expect(page.getByLabel("Timeline reading order")).toHaveValue("asc");
  await expect(cards(page)).toHaveCount(1);
});

test("a default view applies itself on a later visit", async ({ page }) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  await signUp(page, `views-${suffix}@opptrail.test`, "View Saver");

  await page.getByLabel("Filter by stage").selectOption("Negotiation");
  await page.getByRole("button", { name: "Apply" }).click();

  await page
    .getByRole("button", { name: "Save current opportunity view" })
    .click();
  await page.getByLabel("View name").fill("My default");
  await page
    .getByRole("checkbox", { name: "Open this view by default" })
    .check();
  await page.getByRole("button", { name: "Save view" }).click();

  await expect(
    page.getByLabel("Saved opportunity views").locator("option"),
  ).toContainText(["My default (default)"]);

  // Arriving with no filter in the URL is what makes the default apply; a
  // deep link is left alone, which the component tests cover directly.
  await page.goto("/");
  await expect(page).toHaveURL(/opportunities\.stage=Negotiation/);
  await expect(page.getByLabel("Filter by stage")).toHaveValue("Negotiation");
});

test("a view is saved for everyone deliberately, and says so afterwards", async ({
  page,
}) => {
  // Milestone 2.13 (D-076): the author chooses at save time whether a view is
  // theirs or everyone's, and the interface says which it is afterwards -- to
  // the author and, differently, to the colleague it reaches. The reviewer who
  // failed check 08 could tell neither.
  const suffix = Math.random().toString(36).slice(2, 8);
  const name = `Shared ${suffix}`;
  await signIn(page, ALEX);

  await page.getByLabel("Filter by stage").selectOption("Negotiation");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(cards(page)).toHaveCount(1);

  await page
    .getByRole("button", { name: "Save current opportunity view" })
    .click();
  await page.getByLabel("View name").fill(name);
  await page.getByRole("radio", { name: "Everyone" }).check();
  await page.getByRole("button", { name: "Save view" }).click();

  await expect(
    page.getByLabel("Saved opportunity views").locator("option"),
  ).toContainText([`${name} - shared with everyone`]);

  // The colleague is told whose view it is, and that its filters travelled
  // while its rows did not.
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, BLAIR);
  await applySavedView(page, name);

  await expect(page.locator(".applied-view")).toContainText(name);
  await expect(page.locator(".applied-view")).toContainText("shared by");
  await expect(page.locator(".saved-views")).toContainText(
    "shared the filters, not the opportunities",
  );
});

test("editing and deleting a view live behind Manage", async ({ page }) => {
  // D-082: the per-view delete control is off the dashboard. Renaming is what
  // replaces deleting and re-saving, which is the clunkiness the same review
  // reported.
  const suffix = Math.random().toString(36).slice(2, 8);
  await signUp(page, `manage-${suffix}@opptrail.test`, "View Manager");

  await page
    .getByRole("button", { name: "Save current opportunity view" })
    .click();
  await page.getByLabel("View name").fill("First name");
  await page.getByRole("button", { name: "Save view" }).click();

  await expect(
    page.getByRole("button", { name: "Delete view First name" }),
  ).toHaveCount(0);

  await page.getByRole("button", { name: "Manage opportunity views" }).click();
  await expectNoAccessibilityViolations(page, "the manage views dialog");
  await page.getByRole("button", { name: "Edit view First name" }).click();
  await page.getByLabel("View name").fill("Second name");
  await page.getByRole("button", { name: "Save changes" }).click();

  await expect(
    page.getByRole("button", { name: "Delete view Second name" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Delete view Second name" }).click();
  await page.getByRole("button", { name: "Delete view", exact: true }).click();

  await expect(page.locator(".manage-views")).toHaveCount(0);
  await page.getByRole("button", { name: "Close" }).click();
  // The seed's shared views stay in the list, which is the point of them; it
  // is this user's own view that has gone.
  await expect(page.getByLabel("Saved opportunity views")).not.toContainText(
    "Second name",
  );
});
