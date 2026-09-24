import { expect, test } from "@playwright/test";

import {
  ALEX,
  BLAIR,
  NORTHWIND,
  addComment,
  addNote,
  createOpportunity,
  entry,
  expectNoAccessibilityViolations,
  openComposer,
  openTimeline,
  signIn,
  signOut,
  signUp,
} from "./helpers";

/**
 * Milestone 3.3: a discussion that reads as a discussion
 * (`docs/FEATURES.md` §7 — "threaded comments with reactions and
 * resolve/unresolve. Resolve is what keeps a long deal's discussion
 * readable").
 *
 * Two people are needed for the half that matters, so this runs on the
 * seeded deal rather than a fresh one: Alex owns Northwind and Blair edits
 * it, which is the pairing the permission rule (D-128) is about.
 */
test("a question is answered under itself, then closed", async ({ page }) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Threads ${suffix}`;

  await signUp(page, `threads-${suffix}@opptrail.test`, "Thread Tester");
  await createOpportunity(page, opportunity, { account: "Initech" });
  await openTimeline(page, opportunity);

  const created = entry(page, "Opportunity created");
  await addNote(created, "Pricing is not agreed yet.");
  const note = page.locator("section.note-block").first();
  await addComment(note, "What is their budget?");

  const thread = page.locator(".comment-thread").first();
  await expect(thread).toContainText("What is their budget?");

  // The reply goes under the thread, not beside it.
  const reply = await openComposer(thread, "Reply", /^Reply to /);
  await reply.fill("Around 25k, confirmed with procurement.");
  await thread.getByRole("button", { name: "Reply", exact: true }).click();
  await expect(
    thread.locator(".comment-replies .comment-row").first(),
  ).toContainText("Around 25k");

  // Replies are one level deep (D-127): the answer carries no Reply of its
  // own, so the screen never offers what the API refuses.
  await expect(thread.getByRole("button", { name: "Reply" })).toHaveCount(1);

  await thread.getByRole("button", { name: "Resolve" }).click();
  const resolved = page.locator(".comment-thread.is-resolved");
  await expect(resolved).toContainText("Resolved by Thread Tester");
  // Closed means collapsed: the question is off the screen until asked for.
  await expect(page.getByText("What is their budget?")).toBeHidden();

  await resolved.getByRole("button", { name: "Show", exact: true }).click();
  await expect(page.getByText("What is their budget?")).toBeVisible();
  await expect(page.getByText("Around 25k")).toBeVisible();

  await expectNoAccessibilityViolations(
    page,
    "a thread expanded after being resolved",
  );

  await resolved.getByRole("button", { name: "Reopen", exact: true }).click();
  await expect(page.getByText("Resolved by Thread Tester")).toBeHidden();
  await expect(
    thread.getByRole("button", { name: "Reply", exact: true }),
  ).toBeVisible();
});

test("an editor answers the owner's thread but cannot close it", async ({
  page,
}) => {
  const body = `Who signs the pilot clause? ${Math.random()
    .toString(36)
    .slice(2, 8)}`;

  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);
  const note = page.locator("section.note-block").first();
  await addComment(note, body);
  const ownerThread = page
    .locator(".comment-thread")
    .filter({ hasText: body })
    .first();
  await expect(
    ownerThread.getByRole("button", { name: "Resolve" }),
  ).toBeVisible();
  await signOut(page);

  await signIn(page, BLAIR);
  await openTimeline(page, NORTHWIND);
  const asEditor = page
    .locator(".comment-thread")
    .filter({ hasText: body })
    .first();
  const reply = await openComposer(asEditor, "Reply", /^Reply to /);
  await reply.fill("Legal does, once the DPA is signed.");
  await asEditor.getByRole("button", { name: "Reply", exact: true }).click();
  await expect(asEditor).toContainText("Legal does");

  // Author-or-owner (D-128): Blair may answer Alex's question and may close
  // their own threads, but not this one.
  await expect(asEditor.getByRole("button", { name: "Resolve" })).toHaveCount(
    0,
  );
});
