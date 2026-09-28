import { expect, test } from "@playwright/test";
import {
  addNote,
  entry,
  entryForm,
  openEntryForm,
  openTimeline,
  createOpportunity,
  signIn,
  signOut,
  signUp,
} from "./helpers";

/**
 * Critical journey 5 (brief §6.3): an @mention notifies the person mentioned.
 */
test("mentioning a colleague notifies them", async ({ page }) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const ownerEmail = `mention-owner-${suffix}@opptrail.test`;
  const colleagueEmail = `mention-guest-${suffix}@opptrail.test`;
  const opportunity = `Mention ${suffix}`;

  await signUp(page, colleagueEmail, "Mentioned Colleague");
  await signOut(page);

  await signUp(page, ownerEmail, "Mentioning Owner");
  await createOpportunity(page, opportunity, {
    account: "Soylent",
    value: "9000",
    currency: "USD",
  });
  await openTimeline(page, opportunity);

  await page.getByPlaceholder("Colleague email").fill(colleagueEmail);
  await page.getByRole("button", { name: "Share", exact: true }).click();
  await expect(
    page.locator(".share-row").filter({ hasText: colleagueEmail }),
  ).toBeVisible();

  await openEntryForm(page);
  await entryForm(page).getByLabel("Title").fill("Security review");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  await expect(
    page.getByRole("heading", { name: "Security review" }),
  ).toBeVisible();

  await addNote(
    entry(page, "Security review"),
    `@${colleagueEmail} can you take the DPA?`,
  );
  await expect(page.getByText("can you take the DPA?")).toBeVisible();
  await signOut(page);

  await signIn(page, colleagueEmail);
  await page.getByRole("button", { name: "Notifications" }).click();
  const panel = page.locator(".notification-panel");
  await expect(
    panel.getByText("You were mentioned in a timeline update."),
  ).toBeVisible();
});

/**
 * Milestone 1.7: `GET /api/v2/notifications` is full history, not
 * unread-only — marking a notification read must not make it disappear the
 * way v1's `WHERE read = 0` did, and it has to survive a reload since that is
 * the difference between "read" living in the database and living only in
 * the query cache.
 */
test("notification history survives being read, and mark-all-read clears the badge", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const ownerEmail = `notif-owner-${suffix}@opptrail.test`;
  const colleagueEmail = `notif-guest-${suffix}@opptrail.test`;
  const opportunity = `Notify ${suffix}`;

  await signUp(page, colleagueEmail, "Notified Colleague");
  await signOut(page);

  await signUp(page, ownerEmail, "Notifying Owner");
  await createOpportunity(page, opportunity, { account: "Soylent" });
  await openTimeline(page, opportunity);

  await page.getByPlaceholder("Colleague email").fill(colleagueEmail);
  await page.getByRole("button", { name: "Share", exact: true }).click();
  await expect(
    page.locator(".share-row").filter({ hasText: colleagueEmail }),
  ).toBeVisible();

  await openEntryForm(page);
  await entryForm(page).getByLabel("Title").fill("Kickoff");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  const kickoff = entry(page, "Kickoff");
  await expect(kickoff).toBeVisible();

  // One mentioning note is enough: it notifies the colleague both as a
  // mention and as activity on an opportunity shared with them
  // (`routes_timeline.py` calls both `notify_mentions` and
  // `notify_shared_activity`), which is already more than one row — the
  // exact count is an implementation detail this test does not pin.
  await addNote(kickoff, `@${colleagueEmail} kickoff-note-alpha`);
  await expect(page.getByText("kickoff-note-alpha")).toBeVisible();
  await signOut(page);

  await signIn(page, colleagueEmail);
  await page.getByRole("button", { name: "Notifications" }).click();
  const panel = page.locator(".notification-panel");
  const rows = panel.locator(".notification-row");
  const total = await rows.count();
  expect(total).toBeGreaterThanOrEqual(2);
  await expect(
    page.getByRole("button", { name: "Notifications" }),
  ).toContainText(String(total));

  // Marking one read leaves every row on screen — the read one just stops
  // offering the action and picks up the read styling.
  await rows.first().getByRole("button", { name: "Mark read" }).click();
  await expect(rows).toHaveCount(total);
  await expect(rows.first()).toHaveClass(/is-read/);
  await expect(
    rows.first().getByRole("button", { name: "Mark read" }),
  ).toHaveCount(0);

  // The read state reached the database, not just the query cache.
  await page.reload();
  await page.getByRole("button", { name: "Notifications" }).click();
  await expect(panel.locator(".notification-row")).toHaveCount(total);
  await expect(panel.locator(".notification-row").first()).toHaveClass(
    /is-read/,
  );

  await page.getByRole("button", { name: "Mark all read" }).click();
  await expect(panel.locator(".notification-row.is-read")).toHaveCount(total);
  await expect(
    page.getByRole("button", { name: "Mark all read" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Notifications" }),
  ).not.toContainText(/\d/);
});
