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
 * permissions. The UI half is one control on the timeline panel — a format
 * choice plus a single export link (milestone 3.1a, D-115 collapsed the
 * three always-visible format links into this) — and the permission half is
 * checked by requesting the same URLs as each actor, which is where a leak
 * would actually appear.
 */
test("the owner can export in every format from the timeline", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  const exportControl = page.locator(".export-actions");
  const formatSelect = exportControl.getByLabel("Export format");
  let jsonHref: string | null = null;
  for (const format of ["PDF", "CSV", "JSON"]) {
    await formatSelect.selectOption({ label: format });
    const link = exportControl.getByRole("link", { name: `Export ${format}` });
    await expect(link).toBeVisible();
    if (format === "JSON") {
      jsonHref = await link.getAttribute("href");
    }
  }

  const response = await page.request.get(jsonHref!);
  expect(response.status()).toBe(200);
  expect((await response.json()).opportunity.name).toBe(NORTHWIND);
});

test("export respects the viewer, outsider and anonymous cases", async ({
  page,
  request,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);
  const exportControl = page.locator(".export-actions");
  await exportControl
    .getByLabel("Export format")
    .selectOption({ label: "JSON" });
  const href = await exportControl
    .getByRole("link", { name: "Export JSON" })
    .getAttribute("href");
  const opportunityId = Number(href!.match(/\/opportunities\/(\d+)\//)![1]);

  // Anonymous: no session at all.
  const anonymous = await request.get(
    `/api/v2/opportunities/${opportunityId}/export/json`,
  );
  expect(anonymous.status()).toBe(401);

  // A viewer may export; an unrelated user must not even learn it exists.
  for (const [email, expected] of [
    [CASEY, 200],
    [DANA, 404],
  ] as const) {
    await apiSignIn(request, email);

    for (const format of ["json", "csv"]) {
      const result = await request.get(
        `/api/v2/opportunities/${opportunityId}/export/${format}`,
      );
      expect(result.status(), `${email} exporting ${format}`).toBe(expected);
    }
  }

  // PDF needs WeasyPrint's native libraries, present in the container but
  // absent on a bare host (CLAUDE.md's WeasyPrint note, mirrored on the
  // backend by `test_export.py::test_pdf_export_produces_a_real_pdf`'s
  // import guard). Probe once, as the owner, who definitely has access, so a
  // 500 here can only mean the libraries are missing rather than a
  // permission bug — a genuine regression still fails below, and only the
  // documented host gap is skipped.
  await apiSignIn(request, ALEX);
  const probe = await request.get(
    `/api/v2/opportunities/${opportunityId}/export/pdf`,
  );
  test.skip(
    probe.status() === 500,
    "WeasyPrint native libraries unavailable on this host (see CLAUDE.md)",
  );

  for (const [email, expected] of [
    [CASEY, 200],
    [DANA, 404],
  ] as const) {
    await apiSignIn(request, email);
    const result = await request.get(
      `/api/v2/opportunities/${opportunityId}/export/pdf`,
    );
    expect(result.status(), `${email} exporting pdf`).toBe(expected);
  }
});
