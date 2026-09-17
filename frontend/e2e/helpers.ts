import { expect, type APIRequestContext, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/** Seeded by `backend/tools/seed.py`; see `make seed` for the full tour. */
export const DEMO_PASSWORD = "opptrail-demo-123";
export const ALEX = "alex@opptrail.test";
export const BLAIR = "blair@opptrail.test";
export const CASEY = "casey@opptrail.test";
export const DANA = "dana@opptrail.test";

export const NORTHWIND = "Northwind platform rollout";

export async function signIn(page: Page, email: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(DEMO_PASSWORD);
  await page
    .getByRole("button", { name: "Sign in", exact: true })
    .last()
    .click();
  await expect(
    page.getByRole("heading", { name: "Opportunities" }),
  ).toBeVisible();
}

export async function signUp(page: Page, email: string, name: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Sign up", exact: true }).click();
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(
    page.getByRole("heading", { name: "Opportunities" }),
  ).toBeVisible();
}

export async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  // The panel remembers whichever mode was last used, so assert on the shell
  // rather than on a button whose label depends on that memory.
  await expect(page.locator(".auth-panel")).toBeVisible();
}

/** The "New Opportunity" sidebar form. Scoped because several of its field
 * labels ("Stage", "Value") also appear as text elsewhere on the dashboard. */
export function opportunityForm(page: Page) {
  return page.locator("form.sidebar-form");
}

/** The "Add Entry" form inside an open timeline. */
export function entryForm(page: Page) {
  return page.locator("form.timeline-form");
}

/** The card for one opportunity on the stage board. */
export function card(page: Page, name: string) {
  return page
    .locator("article.opportunity-card")
    .filter({ hasText: name })
    .first();
}

/** One timeline entry, addressed by its title. */
export function entry(page: Page, title: string) {
  return page
    .locator("article.timeline-entry")
    .filter({ hasText: title })
    .first();
}

export async function openTimeline(page: Page, name: string) {
  await card(page, name).getByRole("button", { name: "Timeline" }).click();
  await expect(
    page.locator(".timeline-panel").getByRole("heading", { name }),
  ).toBeVisible();
}

/**
 * Signs in over the API rather than the UI, for the checks that are about what
 * the server answers rather than what the page shows.
 *
 * The CSRF cookie is re-read after every unsafe call because logging in
 * rotates it along with the session (`app/auth.py`), so a token captured
 * beforehand is already stale by the next request.
 */
export async function apiSignIn(request: APIRequestContext, email: string) {
  const response = await request.post("/api/auth/login", {
    data: { email, password: DEMO_PASSWORD },
    headers: { "X-CSRF-Token": await csrfToken(request) },
  });
  expect(response.status(), `API sign-in for ${email}`).toBe(200);
}

export async function csrfToken(request: APIRequestContext) {
  await request.get("/api/health");
  const state = await request.storageState();
  const cookie = state.cookies.find(
    (candidate) => candidate.name === "opptrail_csrf",
  );
  expect(
    cookie,
    "the app must issue a CSRF cookie on a safe request",
  ).toBeDefined();
  return cookie!.value;
}

/**
 * Rules whose failures are a known, tracked debt rather than a regression.
 *
 * `color-contrast` fails across the app because the palette in
 * `frontend/app/globals.css` predates any contrast requirement. Fixing it is a
 * design-token change, which the plan assigns to milestone 2.5 (design tokens)
 * and R.2 (axe clean) — not to Phase F, which ships no user-facing change.
 *
 * This list is a ratchet, not an allowlist: any violation of any *other* rule
 * fails the suite immediately, and removing an entry here is the milestone
 * that fixes it. Nothing may be added without the milestone that will remove
 * it again.
 */
export const DEFERRED_AXE_RULES = new Set(["color-contrast"]);

interface ReportedViolation {
  id: string;
  impact: string | null | undefined;
  help: string;
  nodes: string[];
}

async function auditPage(page: Page): Promise<ReportedViolation[]> {
  const results = await new AxeBuilder({ page: page as never })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();

  return results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    nodes: violation.nodes.map((node) => node.target.join(" ")),
  }));
}

/**
 * Accessibility check for the page as it currently stands (brief §3.4, §6.1).
 *
 * WCAG 2.1 AA is the target in brief §8; axe asserts the machine-checkable
 * part of it, which is what can be gated automatically.
 */
export async function expectNoAccessibilityViolations(
  page: Page,
  context: string,
) {
  const violations = await auditPage(page);
  const unexpected = violations.filter(
    (violation) => !DEFERRED_AXE_RULES.has(violation.id),
  );

  expect(unexpected, `axe violations on ${context}`).toEqual([]);
}

/**
 * Asserts a rule is genuinely still broken, so the ratchet above cannot quietly
 * outlive the problem it defers.
 */
export async function expectRuleIsStillDeferred(page: Page, rule: string) {
  const violations = await auditPage(page);
  expect(
    violations.map((violation) => violation.id),
    `${rule} is in DEFERRED_AXE_RULES but no longer fails — remove it from the list`,
  ).toContain(rule);
}
