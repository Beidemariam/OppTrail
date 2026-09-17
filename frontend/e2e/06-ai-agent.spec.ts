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
  const href = await page
    .locator(".export-actions")
    .getByRole("link", { name: "JSON" })
    .getAttribute("href");
  const opportunityId = Number(href!.split("/")[3]);

  await apiSignIn(request, DANA);

  const asked = await request.post(
    `/api/opportunities/${opportunityId}/ai/ask`,
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
