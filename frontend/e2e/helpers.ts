import {
  expect,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";
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

/** The create/edit form, which milestone 2.7 moved into a dialog. Scoped
 * because several of its field labels ("Stage", "Value") also appear as text
 * elsewhere on the dashboard. */
export function opportunityForm(page: Page) {
  return page.locator("form.opportunity-form");
}

/** Opens that dialog from the page header, and hands back the form in it. */
export async function openOpportunityForm(page: Page) {
  await page.getByRole("button", { name: "New opportunity" }).first().click();
  await expect(opportunityForm(page)).toBeVisible();
  return opportunityForm(page);
}

/**
 * Creates one opportunity through the dialog and waits for its card, which is
 * the first step of most of these journeys.
 */
export async function createOpportunity(
  page: Page,
  name: string,
  fields: {
    account?: string;
    value?: string;
    currency?: string;
    stage?: string;
    closeDate?: string;
  } = {},
) {
  const form = await openOpportunityForm(page);
  await form.getByLabel("Opportunity").fill(name);
  await form.getByLabel("Account").fill(fields.account ?? "Initech");
  if (fields.value) {
    await form.getByLabel("Value").fill(fields.value);
  }
  if (fields.currency) {
    await form.getByLabel("Currency").fill(fields.currency);
  }
  if (fields.stage) {
    await form.getByLabel("Stage").selectOption(fields.stage);
  }
  if (fields.closeDate) {
    await form.getByLabel("Expected close").fill(fields.closeDate);
  }
  await form.getByRole("button", { name: "Create opportunity" }).click();
  await expect(form).toBeHidden();
  await expect(card(page, name)).toBeVisible();
}

/** The "Add Entry" form inside an open timeline. */
export function entryForm(page: Page) {
  return page.locator("form.timeline-form");
}

/**
 * A composer, which is collapsed until it is written in (milestone 3.1,
 * `app/RichTextEditor.tsx`).
 *
 * Two steps, because there are two: the control saying what it would add is
 * what a reader sees, and the editable region only exists once that is
 * clicked. The region is addressed by its accessible name — a contenteditable
 * element carries no placeholder attribute, and `aria-label` is what names it.
 */
export async function openComposer(
  scope: Page | Locator,
  trigger: string,
  /** A pattern where the name carries a value — a reply names the person
   * being answered (milestone 3.3). */
  label: string | RegExp,
) {
  await scope.getByRole("button", { name: trigger, exact: true }).click();
  const editor = scope.getByLabel(label);
  await expect(editor).toBeVisible();
  return editor;
}

/** Writes one note on an entry and posts it. */
export async function addNote(scope: Page | Locator, markdown: string) {
  const editor = await openComposer(
    scope,
    "Add note",
    "Add a note to this entry",
  );
  await editor.fill(markdown);
  await scope.getByRole("button", { name: "Add Note" }).click();
  await expect(editor).toBeHidden();
}

/** Writes one comment on a note and posts it. */
export async function addComment(scope: Page | Locator, markdown: string) {
  const editor = await openComposer(
    scope,
    "Add comment",
    "Add a comment to this note",
  );
  await editor.fill(markdown);
  await scope.getByRole("button", { name: "Post" }).click();
  await expect(editor).toBeHidden();
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
  // The card's own name is the link: a real link, not a button, because an
  // opportunity has its own URL from milestone 2.1 onwards and the board
  // stays beside the panel it opens.
  await card(page, name).getByRole("link", { name }).click();
  await expect(
    page.locator(".timeline-panel").getByRole("heading", { name }),
  ).toBeVisible();
}

/**
 * Opens the opportunity's history — the one destination for what happened
 * here since milestone 3.1c (D-121), holding what the activity log, the
 * per-item history dialogs and the sharing panel's audit disclosure used to
 * answer separately.
 *
 * `exact` because the heading's own fields are edit triggers named by their
 * value since 2.11 (D-100), so a deal whose name contains this word would
 * otherwise match two controls in this region.
 */
export async function openHistory(page: Page) {
  await page
    .locator(".timeline-heading")
    .getByRole("button", { name: "History", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "Activity and history" }),
  ).toBeVisible();
  return dialog;
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
  const response = await request.post("/api/v2/auth/login", {
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
 * **Empty, and it is meant to stay that way.** It held `color-contrast` from
 * Phase F (D-026), because the palette predated any contrast requirement and
 * repainting the app inside a test-infrastructure milestone would have
 * pre-empted the token work. Milestone 2.5 did that work — `app/globals.css`
 * now carries the token set from `docs/DESIGN-SYSTEM.md` in both themes, and
 * `lib/contrast.test.ts` measures every pair — so the entry came off and the
 * gate tightened, which is what a ratchet is for.
 *
 * Nothing may be added here without the milestone that will remove it again.
 */
export const DEFERRED_AXE_RULES = new Set<string>();

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
