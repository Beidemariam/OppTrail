import { expect, test } from "@playwright/test";
import {
  entryForm,
  expectNoAccessibilityViolations,
  openTimeline,
  createOpportunity,
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

  await createOpportunity(page, opportunity, {
    account: "Wonka Industries",
    value: "75000",
    currency: "USD",
    stage: "Prospecting",
  });

  await openTimeline(page, opportunity);

  // Creating an opportunity already writes one system entry.
  const timeline = page.locator(".timeline-list");
  await expect(timeline.locator("article.timeline-entry")).toHaveCount(1);
  await expect(timeline.getByText("Opportunity created")).toBeVisible();

  // The opportunity has its own URL (milestone 2.1), so a reload keeps the
  // reader on the timeline they were reading rather than on the dashboard.
  await expect(page).toHaveURL(/\/opportunities\/\d+$/);
  await page.reload();
  await expect(timeline.getByText("Opportunity created")).toBeVisible();

  // Explicit, well-separated event times: the "Event time" input is minute
  // resolution (`lib/time.ts`'s `toLocalInput`), while the system entry
  // carries the full second its create call ran on — leaving them at their
  // shared default of "now" would let the system entry's own seconds sort
  // *after* an entry rounded down to the top of the same minute, which is
  // the input's known granularity, not a claim about typical event spacing.
  const hourFromNow = (hours: number) => {
    const target = new Date(Date.now() + hours * 60 * 60 * 1000);
    const local = new Date(
      target.getTime() - target.getTimezoneOffset() * 60 * 1000,
    );
    return local.toISOString().slice(0, 16);
  };

  for (const [type, title, offsetHours] of [
    ["Call", "Discovery call", 1],
    ["Meeting", "Solution review", 2],
  ] as const) {
    await entryForm(page).getByLabel("Type").selectOption({ label: type });
    await entryForm(page).getByLabel("Title").fill(title);
    await entryForm(page)
      .getByLabel("Body")
      .fill(`Notes from the ${title.toLowerCase()}.`);
    await entryForm(page)
      .getByLabel("Event time")
      .fill(hourFromNow(offsetHours));
    await entryForm(page).getByRole("button", { name: "Add Entry" }).click();
    await expect(timeline.getByRole("heading", { name: title })).toBeVisible();
  }

  await expect(timeline.locator("article.timeline-entry")).toHaveCount(3);

  // Default reading order is newest first (`event_timestamp` descending,
  // `lib/domain.ts`'s `emptyTimelineFilters`, D-115), so the system entry and
  // the two typed entries — each an hour further out than the last — read
  // back in the reverse of the order their event times actually put them in.
  await expect(timeline.locator("article.timeline-entry h3")).toHaveText([
    "Solution review",
    "Discovery call",
    "Opportunity created",
  ]);

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
