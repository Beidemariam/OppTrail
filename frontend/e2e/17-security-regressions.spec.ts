import { expect, test } from "@playwright/test";
import {
  addNote,
  createOpportunity,
  entry,
  entryForm,
  openEntryForm,
  openTimeline,
  signUp,
} from "./helpers";

/**
 * Milestone 2.12 (D-053): the deterministic half of the Phase 1 hand-run
 * user test, folded into the suite as a regression guard rather than a
 * twenty-minutes-a-phase manual check. Two fixed-right-answer security
 * properties live here because neither has a natural home in an existing
 * journey spec.
 */

test("the session cookie is HttpOnly and the CSRF cookie is readable by the client", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  await signUp(page, `cookie-flags-${suffix}@opptrail.test`, "Cookie Tester");

  const cookies = await page.context().cookies();
  const session = cookies.find((cookie) => cookie.name === "opptrail_session");
  const csrf = cookies.find((cookie) => cookie.name === "opptrail_csrf");

  expect(session, "the session cookie must be issued on sign-up").toBeDefined();
  expect(session?.httpOnly, "the session cookie must be HttpOnly").toBe(true);

  // Double-submit cookie (`app/security.py`): the SPA has to read this one
  // itself to echo it back in `X-CSRF-Token`, so it cannot be HttpOnly.
  expect(csrf, "the CSRF cookie must be issued").toBeDefined();
  expect(csrf?.httpOnly, "the CSRF cookie must be readable by the client").toBe(
    false,
  );
});

/**
 * `MarkdownText.test.tsx` already proves the sanitizer strips a
 * `javascript:` link and drops raw HTML in isolation. What that unit test
 * cannot see is the real round trip this exercises: through the actual form,
 * stored as-is by an API that sanitizes nothing on write, and made safe only
 * when a real browser renders it back.
 *
 * Milestone 3.1 added a second layer in front of it, and this journey now
 * checks both — because the first one is not a boundary. The composer refuses
 * to *make* a link on a protocol the renderer would strip (`lib/markdown.ts`
 * shares one `linkProtocols` list with the sanitizer), so hostile Markdown
 * typed in stays inert text. But content does not only arrive through the
 * composer — the API takes whatever a client sends, and Phase 5 will ingest
 * email — so the same payload is also posted straight to the API, where the
 * only thing between it and the reader is the sanitizer.
 */
test("hostile note content cannot run a script or leave a live javascript: link", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Hostile ${suffix}`;
  const dialogs: string[] = [];
  page.on("dialog", (dialog) => {
    dialogs.push(dialog.message());
    void dialog.dismiss();
  });

  await signUp(page, `hostile-${suffix}@opptrail.test`, "Hostile Tester");
  await createOpportunity(page, opportunity, { account: "Initech" });
  await openTimeline(page, opportunity);

  await openEntryForm(page);
  await entryForm(page).getByLabel("Title").fill("Follow-up");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  const followUp = entry(page, "Follow-up");
  await expect(followUp).toBeVisible();

  const hostile =
    "Reminder: <img src=x onerror=\"alert('xss')\"> [click here](javascript:alert('nav')) to confirm.";

  // --- Typed into the composer ------------------------------------------
  await addNote(followUp, hostile);

  const typed = page
    .locator("section.note-block")
    .filter({ hasText: "Reminder" });
  await expect(typed).toBeVisible();

  // Nothing executed while rendering the stored content.
  expect(dialogs).toEqual([]);

  // The words survive as words: the editor refused the link outright rather
  // than storing one for the sanitizer to disarm, so there is no anchor at all
  // (milestone 3.1).
  await expect(typed.getByText("click here")).toBeVisible();
  await expect(typed.locator("a")).toHaveCount(0);

  // --- Posted straight to the API, never seen by the composer -----------
  const opportunityId = new URL(page.url()).pathname.split("/").pop();
  const timeline = await page.request.get(
    `/api/v2/opportunities/${opportunityId}/timeline`,
  );
  expect(timeline.status()).toBe(200);
  const items = (await timeline.json()).items as Array<{
    id: number;
    title: string;
  }>;
  const entryId = items.find((item) => item.title === "Follow-up")!.id;
  const cookies = await page.context().cookies();
  const csrf = cookies.find((cookie) => cookie.name === "opptrail_csrf")!.value;
  const posted = await page.request.post(`/api/v2/timeline/${entryId}/notes`, {
    data: { body: `Bypass: ${hostile}` },
    headers: { "X-CSRF-Token": csrf },
  });
  expect(posted.status(), "the API stores what it is sent").toBe(201);

  await page.reload();
  const stored = page
    .locator("section.note-block")
    .filter({ hasText: "Bypass" });
  await expect(stored).toBeVisible();
  expect(dialogs).toEqual([]);

  // The link text is legitimate content and survives; its href does not. Not
  // addressed by role: an <a> with no href attribute has no implicit link
  // role, which is the point — the sanitizer removed the attribute rather
  // than merely rewriting it.
  const link = stored.locator("a").filter({ hasText: "click here" });
  await expect(link).toHaveCount(1);
  await expect(link).not.toHaveAttribute("href", /javascript:/);
  await expect(stored.locator("img")).toHaveCount(0);
});
