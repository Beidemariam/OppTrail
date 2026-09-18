import { expect, test, type Page } from "@playwright/test";
import {
  ALEX,
  CASEY,
  DANA,
  expectNoAccessibilityViolations,
  signIn,
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
  await page.getByRole("button", { name: "Search" }).click();
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
