import { expect, test } from "@playwright/test";
import {
  ALEX,
  CASEY,
  DANA,
  NORTHWIND,
  apiSignIn,
  openTimeline,
  signIn,
} from "./helpers";

/**
 * Critical journey 11 (brief §6.3): CSV, JSON and PDF export respect
 * permissions. The UI half is three links on the timeline panel; the
 * permission half is checked by requesting the same URLs as each actor, which
 * is where a leak would actually appear.
 */
test("the owner can export in every format from the timeline", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  const links = page.locator(".export-actions");
  for (const format of ["PDF", "CSV", "JSON"]) {
    await expect(links.getByRole("link", { name: format })).toBeVisible();
  }

  const href = await links
    .getByRole("link", { name: "JSON" })
    .getAttribute("href");
  const response = await page.request.get(href!);
  expect(response.status()).toBe(200);
  expect((await response.json()).opportunity.name).toBe(NORTHWIND);
});

test("export respects the viewer, outsider and anonymous cases", async ({
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

  // Anonymous: no session at all.
  const anonymous = await request.get(
    `/api/opportunities/${opportunityId}/export/json`,
  );
  expect(anonymous.status()).toBe(401);

  // A viewer may export; an unrelated user must not even learn it exists.
  for (const [email, expected] of [
    [CASEY, 200],
    [DANA, 404],
  ] as const) {
    await apiSignIn(request, email);

    for (const format of ["json", "csv", "pdf"]) {
      const result = await request.get(
        `/api/opportunities/${opportunityId}/export/${format}`,
      );
      expect(result.status(), `${email} exporting ${format}`).toBe(expected);
    }
  }
});
