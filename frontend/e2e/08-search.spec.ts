import { expect, test, type Page } from "@playwright/test";
import {
  ALEX,
  CASEY,
  DANA,
  addComment,
  addNote,
  createOpportunity,
  entry,
  expectNoAccessibilityViolations,
  openTimeline,
  signIn,
  signUp,
} from "./helpers";

/**
 * Critical journey 6 (brief §6.3): "Search finds opportunities and entries the
 * user can access, and nothing else."
 *
 * The seeded corpus makes the isolation checkable by name: "finance" appears
 * in a Northwind comment and in an Initech note (`backend/tools/seed.py`), so
 * Alex sees both, Casey — a viewer on Northwind only — sees one, and Dana, who
 * has access to nothing, sees none.
 */

const NORTHWIND = "Northwind platform rollout";
const INITECH = "Initech expansion";

function results(page: Page) {
  return page.locator("article.search-result");
}

/** The query box, addressed by role: the results region is labelled "Search
 * results", so a label lookup for "Search" alone matches both. */
function queryBox(page: Page) {
  return page.getByRole("textbox", { name: "Search" });
}

async function searchFor(page: Page, term: string) {
  await queryBox(page).fill(term);
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

test("search spans the opportunities a user can read, and no others", async ({
  page,
}) => {
  await signIn(page, ALEX);

  await page.getByRole("link", { name: "Search" }).click();
  await expect(page).toHaveURL(/\/search$/);
  await expect(results(page)).toHaveCount(0);

  await searchFor(page, "finance");

  await expect(results(page)).toHaveCount(2);
  await expect(results(page).filter({ hasText: NORTHWIND })).toHaveCount(1);
  await expect(results(page).filter({ hasText: INITECH })).toHaveCount(1);

  // The match itself is marked up, which is the "snippeted" half of the
  // acceptance line.
  await expect(results(page).first().locator("mark").first()).toHaveText(
    /finance/i,
  );

  // The query is in the URL, so the search is linkable and the back button
  // walks it (ADR 0005).
  await expect(page).toHaveURL(/\/search\?q=finance$/);
  await expectNoAccessibilityViolations(page, "search results");
});

test("a result opens the match it found, not just the deal", async ({
  page,
}) => {
  // The click-through milestone 1.5 deferred because no opportunity had a URL
  // yet (D-039), landing on the deal from 2.1 and on the *match* from 6.0 --
  // the human's report at the Phase 4 gate. The assertion below used to be
  // `/opportunities/\d+$`, which is precisely the behaviour that was wrong:
  // a reader arriving at the top of a long timeline has been answered without
  // being shown the answer.
  await signIn(page, ALEX);
  await page.goto("/search?q=finance");

  await results(page)
    .filter({ hasText: NORTHWIND })
    .getByRole("link", { name: NORTHWIND })
    .click();

  // Whichever level matched -- the point is that the URL names one.
  await expect(page).toHaveURL(
    /\/opportunities\/\d+\?(entry|note|comment)=\d+$/,
  );
  await expect(
    page.locator(".record-header").getByRole("heading", { name: NORTHWIND }),
  ).toBeVisible();
  // And the reader can see which row it was: the mark is the whole feature.
  await expect(page.locator(".is-linked").first()).toBeVisible();
});

test("a link to a comment opens the resolved thread holding it", async ({
  page,
}) => {
  // The one case where the match can be *hidden* when the reader arrives: a
  // resolved thread collapses to one line (milestone 3.3), so a link into one
  // has to open it for reading. Opened, not reopened -- resolving is a state
  // change for everybody (D-128), so the outcome line stays on screen.
  //
  // The data is built here rather than taken from the seed: this started out
  // conditional on the seed happening to hold a comment that matched, which
  // skipped, and a skipped test is no test at all -- least of all for the one
  // case the milestone is least likely to get right.
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Deep link ${suffix}`;
  // A word nothing else in the database contains, so the search below finds
  // exactly one row and the test is not at the mercy of the seed's wording.
  const needle = `zarquon${suffix}`;

  await signUp(page, `deeplink-${suffix}@opptrail.test`, "Deep Linker");
  await createOpportunity(page, opportunity, { account: "Initech" });
  await openTimeline(page, opportunity);

  const created = entry(page, "Opportunity created");
  await addNote(created, "Pricing is not agreed yet.");
  const note = page.locator("section.note-block").first();
  await addComment(note, `Chased procurement about ${needle}.`);

  const thread = page.locator(".comment-thread").first();
  await thread.getByRole("button", { name: "Resolve" }).click();
  await expect(page.locator(".comment-thread.is-collapsed")).toContainText(
    "Resolved by Deep Linker",
  );
  // Collapsed means the body really is off screen, which is what makes the
  // assertion after the click worth making.
  await expect(page.getByText(needle, { exact: false })).toBeHidden();

  await page.goto(`/search?q=${needle}`);
  await results(page).first().getByRole("link").click();

  await expect(page).toHaveURL(/\?comment=\d+$/);
  await expect(page.locator(".comment-row.is-linked")).toContainText(needle);
  // Opened for reading, not reopened for everybody: the thread still says it
  // is resolved, and Reopen is still the control that would change that.
  await expect(page.getByText("Resolved by Deep Linker")).toBeVisible();
});

test("a viewer sees only the match inside the opportunity shared with them", async ({
  page,
}) => {
  await signIn(page, CASEY);
  await page.getByRole("link", { name: "Search" }).click();
  await searchFor(page, "finance");

  await expect(results(page)).toHaveCount(1);
  await expect(results(page)).toContainText(NORTHWIND);
  await expect(page.getByText(INITECH)).toHaveCount(0);
});

test("a user with no access finds nothing", async ({ page }) => {
  await signIn(page, DANA);
  await page.getByRole("link", { name: "Search" }).click();
  await searchFor(page, "finance");

  await expect(page.getByText("No matches for")).toBeVisible();
  await expect(results(page)).toHaveCount(0);
});

test("a deep link into the search route loads and runs the search", async ({
  page,
}) => {
  // Nothing is exported at /search: FastAPI answers the unmatched path with
  // the one shell (`main.py`'s `serve_frontend`) and the client router reads
  // the query out of the URL.
  await signIn(page, ALEX);
  await page.goto("/search?q=finance");

  await expect(results(page)).toHaveCount(2);
  await expect(queryBox(page)).toHaveValue("finance");
});

test("an unmatched path lands on the dashboard rather than a dead page", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await page.goto("/opportunities/1/board");

  await expect(
    page.getByRole("heading", { name: "Opportunities" }),
  ).toBeVisible();
});
