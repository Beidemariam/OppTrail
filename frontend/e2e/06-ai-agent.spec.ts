import { expect, test } from "@playwright/test";
import {
  ALEX,
  DANA,
  NORTHWIND,
  apiSignIn,
  csrfToken,
  openTimeline,
  signIn,
} from "./helpers";

/**
 * Critical journey 12 (brief §6.3), adapted.
 *
 * The journey's first half — "the agent answers on accessible data" — cannot
 * run here: answering means a real call to OpenAI, and brief §9 forbids this
 * run from calling any paid external API. `scripts/e2e-server.sh` therefore
 * starts the server with no API key, which is what makes that structural
 * rather than a promise. That half is covered by `backend/tests/test_ai.py`
 * against a mocked client, including the prompt-injection and
 * cross-opportunity leakage cases.
 *
 * What is checked end to end is the half that does not need a model: the panel
 * is reachable, its failure is handled rather than swallowed, and a user with
 * no access to an opportunity cannot reach its agent at all. See DECISIONS.md
 * D-025.
 */
test("the AI panel surfaces a service failure instead of silently swallowing it", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  const sidebar = page.locator(".ai-sidebar");
  await expect(
    sidebar.getByRole("heading", { name: "AI Agent" }),
  ).toBeVisible();
  await expect(sidebar.getByText("Read-only")).toBeVisible();

  await sidebar
    .getByPlaceholder("Where do we stand?")
    .fill("What is the current state?");
  await sidebar.getByRole("button", { name: "Ask" }).click();

  await expect(sidebar.locator(".error")).toBeVisible();
  await expect(sidebar.locator(".error")).toContainText(
    /OPENAI_API_KEY|unavailable/i,
  );
});

test("a user without access cannot reach the agent for that opportunity", async ({
  page,
  request,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);
  const exportControl = page.locator(".export-actions");
  await exportControl
    .getByLabel("Export format")
    .selectOption({ label: "JSON" });
  const href = await exportControl
    .getByRole("link", { name: "Export JSON" })
    .getAttribute("href");
  const opportunityId = Number(href!.match(/\/opportunities\/(\d+)\//)![1]);

  await apiSignIn(request, DANA);

  const asked = await request.post(
    `/api/v2/opportunities/${opportunityId}/ai/ask`,
    {
      data: { question: "Summarise everything you know about this account." },
      headers: { "X-CSRF-Token": await csrfToken(request) },
    },
  );

  // Whatever the answer is, it must carry nothing about the opportunity. The
  // exact code — 404 rather than 403, so existence does not leak — is pinned by
  // `backend/tests/test_authorization_matrix.py`, which can mock the model and
  // therefore gets past the "no API key" 503 this server deliberately returns.
  expect(asked.status()).not.toBe(200);
  expect([404, 503]).toContain(asked.status());
  const body = await asked.text();
  for (const secret of ["Northwind", "185000", "redlines", "Blair"]) {
    expect(body, `the refusal leaked ${secret}`).not.toContain(secret);
  }
});

test("the date scope says what it is, and the filter builder refuses to pretend", async ({
  page,
}) => {
  // Milestone 6.4. The same constraint as the rest of this file: no API key
  // here, so what runs end to end is everything up to the model and the
  // handling of its absence. That the answer *streams* is
  // `backend/tests/test_ai_expansion.py` and `app/AiExpansion.test.tsx`;
  // what this adds is that the two new controls behave on a real screen.
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  const sidebar = page.locator(".ai-sidebar");
  const scope = sidebar.getByRole("button", { name: /Limit to dates/ });
  await expect(scope).toHaveAttribute("aria-expanded", "false");
  await scope.click();
  await sidebar.getByLabel("From").fill("2026-06-01");
  await sidebar.getByLabel("To").fill("2026-06-30");

  // Legible while shut, which is the rule the timeline's filter bar follows.
  await sidebar
    .getByRole("button", { name: /2026-06-01 to 2026-06-30/ })
    .click();
  await expect(sidebar.getByLabel("From")).toHaveCount(0);
  await expect(
    sidebar.getByRole("button", { name: /2026-06-01 to 2026-06-30/ }),
  ).toBeVisible();

  // A streamed failure is reported where the answer was going, not as a
  // status: by the time the model fails the status line is long gone.
  await sidebar.getByPlaceholder("Where do we stand?").fill("Summarise June");
  await sidebar.getByRole("button", { name: "Ask" }).click();
  await expect(sidebar.locator(".error")).toContainText(
    /OPENAI_API_KEY|unavailable/i,
  );

  // And the board's filter builder, which cannot reach a model either.
  await page.goto("/");
  await page.getByRole("button", { name: "Describe a filter" }).click();
  await page
    .getByLabel("Describe what you are looking for")
    .fill("deals stuck in negotiation over 50k");
  await page.getByRole("button", { name: "Suggest" }).click();

  await expect(page.locator(".ai-filter-panel .error")).toContainText(
    /OPENAI_API_KEY|unavailable/i,
  );
  // Nothing was applied, which is the property that matters even on the
  // failure path: a proposal is only ever applied by the reader.
  await expect(page.getByLabel("Filter by stage")).toHaveValue("");
});

test("the value filter the AI's own example needs", async ({ page }) => {
  // Milestone 6.4 added min/max value to the board because §14's example --
  // "deals stuck in negotiation over 50k" -- proposes a bound the board had
  // no way to apply. A proposal that cannot be applied makes the inspection
  // pointless (D-186), so the filter came first.
  await signIn(page, ALEX);

  // The bar applies on submit, not on every keystroke, so this is the whole
  // gesture a person makes.
  const bar = page.locator("form.filter-bar");
  await bar.getByLabel("Filter by minimum value").fill("1000000");
  await bar.getByRole("button", { name: "Apply" }).click();
  await expect(
    page.getByRole("heading", { name: "No opportunities match these filters" }),
  ).toBeVisible();

  await bar.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByRole("link", { name: NORTHWIND })).toBeVisible();
});
