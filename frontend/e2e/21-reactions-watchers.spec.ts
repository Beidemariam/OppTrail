import { expect, test } from "@playwright/test";

import {
  addComment,
  addNote,
  createOpportunity,
  entry,
  entryForm,
  openEntryForm,
  expectNoAccessibilityViolations,
  openTimeline,
  signIn,
  signOut,
  signUp,
} from "./helpers";

/**
 * Milestone 3.3a: reactions and watchers, the other half of the roadmap's
 * "threaded comments with reactions ... watchers" line 3.3 split off
 * (D-126). `docs/FEATURES.md` §7 names two things — a reaction on a comment,
 * and following a deal you are not shared on — that neither have anything to
 * do with each other beyond both being collaboration signals rather than
 * content, so one journey covers both against a fresh opportunity.
 */
test("reacts to a comment, and follows a deal with no share on it at all", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const ownerEmail = `react-owner-${suffix}@opptrail.test`;
  const outsiderEmail = `react-outsider-${suffix}@opptrail.test`;
  const opportunity = `Reactions ${suffix}`;

  await signUp(page, ownerEmail, "Reaction Owner");
  await createOpportunity(page, opportunity, { account: "Initech" });
  await openTimeline(page, opportunity);
  const opportunityUrl = page.url();

  await openEntryForm(page);
  await entryForm(page).getByLabel("Title").fill("Kickoff");
  await entryForm(page).getByLabel("Body").fill("First conversation.");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  await addNote(entry(page, "Kickoff"), "Pricing is not agreed yet.");
  const note = page.locator("section.note-block").first();
  await addComment(note, "What is their budget?");

  const thread = page.locator(".comment-thread").first();
  await expect(thread).toContainText("What is their budget?");

  // Reacting is a picker, not seven buttons up front (progressive
  // disclosure) — opening it reveals the fixed set, and choosing one posts
  // it and closes the picker.
  await thread.getByRole("button", { name: "React" }).click();
  await thread.getByRole("button", { name: "React with 👍" }).click();
  const pill = thread.getByRole("button", { name: "Remove your 👍 reaction" });
  await expect(pill).toHaveText("👍 1");

  await expectNoAccessibilityViolations(
    page,
    "a comment with a reaction on it",
  );

  // A second click withdraws the caller's own reaction (toggle, not a
  // second reaction from the same person).
  await pill.click();
  await expect(
    thread.getByRole("button", { name: "Remove your 👍 reaction" }),
  ).toHaveCount(0);
  await expect(thread.getByRole("button", { name: "React" })).toBeVisible();

  await signOut(page);

  // An outsider with no share at all: the opportunity itself 404s, but
  // `docs/FEATURES.md` §7's "follow an opportunity you are not shared on" is
  // reachable from that same screen (D-129).
  await signUp(page, outsiderEmail, "Reaction Outsider");
  await page.goto(opportunityUrl);
  await expect(
    page.getByRole("heading", { name: "This opportunity is not available." }),
  ).toBeVisible();

  const follow = page.getByRole("button", { name: "Follow this opportunity" });
  await expect(follow).toBeVisible();
  await expectNoAccessibilityViolations(
    page,
    "the not-available screen with a watch toggle",
  );
  await follow.click();
  await expect(
    page.getByRole("button", { name: "Following - stop" }),
  ).toBeVisible();

  // Watching grants no access: the deal is still unreadable to this user.
  await expect(
    page.getByRole("heading", { name: "This opportunity is not available." }),
  ).toBeVisible();

  await signOut(page);

  // The owner sees who is watching — owner-only, the same visibility rule
  // as the share list beside it.
  await signIn(page, ownerEmail);
  await openTimeline(page, opportunity);
  await expect(
    page.locator(".watcher-row").filter({ hasText: outsiderEmail }),
  ).toBeVisible();
});
