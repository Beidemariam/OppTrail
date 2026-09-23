import { expect, test } from "@playwright/test";
import {
  createOpportunity,
  entry,
  entryForm,
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
 * cannot see is the real round trip this exercises: typed into the actual
 * form, posted through the API, stored as-is (`sanitize.py` is not yet on
 * this write path — Phase 3's rich text editor is what changes that), and
 * sanitized only when a real browser renders it back.
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

  await entryForm(page).getByLabel("Title").fill("Follow-up");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  const followUp = entry(page, "Follow-up");
  await expect(followUp).toBeVisible();

  await followUp
    .getByPlaceholder("Add note")
    .fill(
      "Reminder: <img src=x onerror=\"alert('xss')\"> [click here](javascript:alert('nav')) to confirm.",
    );
  await followUp.getByRole("button", { name: "Add Note" }).click();

  const note = page
    .locator("section.note-block")
    .filter({ hasText: "Reminder" });
  await expect(note).toBeVisible();

  // Nothing executed while rendering the stored content.
  expect(dialogs).toEqual([]);

  // The link text is legitimate content and survives; its href does not. Not
  // addressed by role: an <a> with no href attribute has no implicit link
  // role, which is the point — the sanitizer removed the attribute rather
  // than merely rewriting it.
  const link = note.locator("a").filter({ hasText: "click here" });
  await expect(link).toHaveCount(1);
  await expect(link).not.toHaveAttribute("href", /javascript:/);
});
