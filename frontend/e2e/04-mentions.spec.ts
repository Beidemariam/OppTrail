import { expect, test } from "@playwright/test";
import {
  entry,
  entryForm,
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

  await entryForm(page).getByLabel("Title").fill("Security review");
  await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
  await expect(
    page.getByRole("heading", { name: "Security review" }),
  ).toBeVisible();

  const review = entry(page, "Security review");
  await review
    .getByPlaceholder("Add note")
    .fill(`@${colleagueEmail} can you take the DPA?`);
  await review.getByRole("button", { name: "Add Note" }).click();
  await expect(page.getByText("can you take the DPA?")).toBeVisible();
  await signOut(page);

  await signIn(page, colleagueEmail);
  await page.getByRole("button", { name: "Notifications" }).click();
  const panel = page.locator(".notification-panel");
  await expect(
    panel.getByText("You were mentioned in a timeline update."),
  ).toBeVisible();
});
