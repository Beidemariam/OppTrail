import { expect, test } from "@playwright/test";

import {
  ALEX,
  expectNoAccessibilityViolations,
  signIn,
  signUp,
} from "./helpers";

/**
 * The reports screen (milestone 6.2, `docs/FEATURES.md` §10).
 *
 * The arithmetic is asserted in `backend/tests/test_dashboard.py`, including
 * §10's 300 ms budget at its own scale. What this adds is the half no unit
 * test reaches: that six aggregations computed by the API arrive on a real
 * screen, drawn, labelled, and permission-filtered per reader.
 */
test("the six aggregations are drawn for the deals this reader can see", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await page.getByRole("link", { name: "Reports" }).click();
  await expect(page).toHaveURL(/\/reports$/);

  for (const report of [
    "Pipeline by stage",
    "Win and loss",
    "Forecast",
    "Average time in stage",
    "Gone quiet",
    "Activity per person",
  ]) {
    await expect(page.getByRole("region", { name: report })).toBeVisible();
  }

  // The seeded corpus has deals in several stages, so the pipeline has bars.
  const pipeline = page.getByRole("region", { name: "Pipeline by stage" });
  await expect(pipeline.locator(".bar-fill").first()).toBeVisible();

  // Alex owns and is shared on the seeded deals, so activity is attributable.
  await expect(
    page.getByRole("region", { name: "Activity per person" }),
  ).toContainText("Alex");

  await expectNoAccessibilityViolations(page, "reports");
});

test("a reader with no deals gets zeroes rather than somebody else's numbers", async ({
  page,
}) => {
  // The dashboard is the second read in the app that spans opportunities, so
  // permissions are inside each query. A fresh account sees its own nothing.
  const suffix = Math.random().toString(36).slice(2, 8);
  await signUp(page, `reports-${suffix}@opptrail.test`, "New Manager");
  await page.getByRole("link", { name: "Reports" }).click();

  await expect(
    page.getByRole("region", { name: "Win and loss" }),
  ).toContainText("Nothing closed yet");
  await expect(page.getByRole("region", { name: "Gone quiet" })).toContainText(
    "Nothing has been silent",
  );
  await expect(
    page.getByRole("region", { name: "Average time in stage" }),
  ).toContainText("No stage change has been recorded yet");
});

test("an unmeasured stage is labelled, never drawn as zero", async ({
  page,
}) => {
  // §10's own caveat: time in stage "is only correct back to the point
  // stage-change entries began being recorded; earlier history is absent and
  // should be labelled as such rather than silently shown as zero."
  await signIn(page, ALEX);
  await page.goto("/reports");

  const card = page.getByRole("region", { name: "Average time in stage" });
  await expect(card).toBeVisible();
  // Never "0 days": an unmeasured stage says so, and a genuinely same-day
  // span says "Less than a day" -- which is a different fact, and the
  // distinction §10 asks to be kept. The first version of this assertion
  // forbade "0 days" and would have passed for the wrong reason, because the
  // seeded data happens to have no sub-day span; the human's own data does.
  await expect(card.getByText("0 days")).toHaveCount(0);
  await expect(card.getByText("Not yet measured").first()).toBeVisible();
  // Either it has measured something and says since when, or it says it has
  // measured nothing.
  await expect(card).toContainText(
    /Measured from stage changes recorded since|No stage change has been recorded yet/,
  );
});
