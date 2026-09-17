import { expect, test } from "@playwright/test";
import {
  entryForm,
  expectNoAccessibilityViolations,
  openTimeline,
  opportunityForm,
  signUp,
} from "./helpers";

/**
 * Critical journey 1 (brief §6.3): sign up, create an opportunity, add typed
 * entries, change the stage, and see the system entry the change generates.
 */
test("sign up, create an opportunity, add entries, change stage", async ({
  page,
}) => {
  const suffix = Math.random().toString(36).slice(2, 8);
  const opportunity = `Lifecycle ${suffix}`;

  await signUp(page, `lifecycle-${suffix}@opptrail.test`, "Lifecycle Tester");

  // A brand new account starts with nothing.
  await expect(page.locator("article.opportunity-card")).toHaveCount(0);
  await expectNoAccessibilityViolations(page, "empty dashboard");

  const form = opportunityForm(page);
  await form.getByLabel("Opportunity").fill(opportunity);
  await form.getByLabel("Account").fill("Wonka Industries");
  await form.getByLabel("Value").fill("75000");
  await form.getByLabel("Currency").fill("USD");
  await form.getByLabel("Stage").selectOption("Prospecting");
  await form.getByRole("button", { name: "Create opportunity" }).click();

  await expect(
    page.locator("article.opportunity-card").filter({ hasText: opportunity }),
  ).toBeVisible();

  await openTimeline(page, opportunity);

  // Creating an opportunity already writes one system entry.
  const timeline = page.locator(".timeline-list");
  await expect(timeline.locator("article.timeline-entry")).toHaveCount(1);
  await expect(timeline.getByText("Opportunity created")).toBeVisible();

  for (const [type, title] of [
    ["Call", "Discovery call"],
    ["Meeting", "Solution review"],
  ] as const) {
    await entryForm(page).getByLabel("Type").selectOption({ label: type });
    await entryForm(page).getByLabel("Title").fill(title);
    await entryForm(page)
      .getByLabel("Body")
      .fill(`Notes from the ${title.toLowerCase()}.`);
    await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
    await expect(timeline.getByRole("heading", { name: title })).toBeVisible();
  }

  await expect(timeline.locator("article.timeline-entry")).toHaveCount(3);

  // Changing the stage must append a system entry nobody can edit.
  await page
    .locator("article.opportunity-card")
    .filter({ hasText: opportunity })
    .getByRole("button", { name: "Edit" })
    .click();
  await opportunityForm(page).getByLabel("Stage").selectOption("Proposal");
  await opportunityForm(page)
    .getByRole("button", { name: "Save changes" })
    .click();

  await openTimeline(page, opportunity);
  const systemEntry = timeline
    .locator("article.timeline-entry")
    .filter({ hasText: "Stage changed to Proposal" });
  await expect(systemEntry).toBeVisible();
  await expect(systemEntry.getByText("System")).toBeVisible();
  await expect(systemEntry.getByRole("button", { name: "Edit" })).toHaveCount(
    0,
  );
  await expect(systemEntry.getByRole("button", { name: "Delete" })).toHaveCount(
    0,
  );

  await expectNoAccessibilityViolations(page, "timeline with entries");
});
