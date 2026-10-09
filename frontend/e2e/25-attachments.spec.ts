import { expect, test } from "@playwright/test";

import {
  ALEX,
  DANA,
  NORTHWIND,
  entry,
  openTimeline,
  signIn,
  signOut,
} from "./helpers";

/**
 * Attachments end to end (milestone 4.3, ADR 0008, `docs/FEATURES.md` §6).
 *
 * What the unit tests cannot reach: a real multipart upload through the real
 * middleware stack (CSRF included), the bytes coming back down the authorized
 * route with the headers that force a download, and the two refusals that are
 * decided by what the file *is* rather than by what it was called.
 */

const PDF = Buffer.from("%PDF-1.7\nquarterly proposal\n");

/** A seeded entry on Northwind (`backend/tools/seed.py`) -- the one a proposal
 * document actually belongs to, which is the point of attaching to an entry
 * rather than to the deal. */
const PROPOSAL = "Proposal sent";

async function attach(
  page: import("@playwright/test").Page,
  entryTitle: string,
  file: { name: string; mimeType: string; buffer: Buffer },
) {
  const card = entry(page, entryTitle);
  await card.getByRole("button", { name: "Attach file" }).click();
  await card.getByLabel("Choose a file").setInputFiles(file);
  return card;
}

test("attach a proposal, read it back, and download it", async ({ page }) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);
  const card = await attach(page, PROPOSAL, {
    name: "quarterly proposal.pdf",
    mimeType: "application/pdf",
    buffer: PDF,
  });

  const link = card.getByRole("link", { name: "quarterly proposal.pdf" });
  await expect(link).toBeVisible();
  // Addressed by name rather than by position: the seed already puts
  // `Northwind proposal.pdf` on this entry, so the entry has two rows and
  // `.attachment-row` alone would match both.
  const row = card
    .locator(".attachment-row")
    .filter({ hasText: "quarterly proposal.pdf" });
  // The size is the client's own reading of `byte_size`, and the uploader is
  // the row's own.
  await expect(row).toContainText("bytes");
  await expect(row).toContainText("Alex");

  // The download is the only way bytes leave the volume (ADR 0008): the file
  // is never a static path, so this href is the authorized route and the
  // response carries what makes a browser save rather than render.
  const href = await link.getAttribute("href");
  expect(href).toMatch(/^\/api\/v2\/attachments\/\d+\/download$/);
  const response = await page.request.get(href!);
  expect(response.status()).toBe(200);
  expect(response.headers()["content-disposition"]).toContain("attachment;");
  expect(response.headers()["x-content-type-options"]).toBe("nosniff");
  expect(await response.body()).toEqual(PDF);
});

test("attach while writing the entry, which is where a person looks", async ({
  page,
}) => {
  // Milestone 4.3a. The control the card carries is for a file that arrives
  // later; this is the one for the file that is already to hand, and it is the
  // place the reviewer looked for it twice.
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);

  await page.getByRole("button", { name: "New entry" }).click();
  const form = page.locator("form.timeline-form");
  await form.getByLabel("Title").fill("Contract countersigned");
  await form.getByLabel("Attach a file (optional)").setInputFiles({
    name: "countersigned.pdf",
    mimeType: "application/pdf",
    buffer: PDF,
  });
  await form.getByRole("button", { name: "Add Entry" }).click();

  const card = entry(page, "Contract countersigned");
  await expect(
    card.getByRole("link", { name: "countersigned.pdf" }),
  ).toBeVisible();
});

test("a renamed executable is refused on its bytes", async ({ page }) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);
  const card = await attach(page, PROPOSAL, {
    name: "report.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from([0x4d, 0x5a, 0x90, 0x00, 0x03, 0x00, 0x00, 0x00]),
  });

  // The roadmap's acceptance criterion for this phase. Nothing the client
  // declared is consulted -- the sniffed bytes decide, and the picker stays
  // open with the reason beside it.
  await expect(card.getByText("Unsupported file type")).toBeVisible();
  await expect(card.getByRole("link", { name: "report.pdf" })).toHaveCount(0);
});

test("someone not on the deal cannot download its files", async ({ page }) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);
  const card = await attach(page, PROPOSAL, {
    name: "contract.pdf",
    mimeType: "application/pdf",
    buffer: PDF,
  });
  const href = await card
    .getByRole("link", { name: "contract.pdf" })
    .getAttribute("href");
  await signOut(page);

  // Dana is the seeded user with access to nothing (`make seed`'s tour calls
  // them "the case worth checking by hand"), so this is the ordinary 404:
  // absence of access never says whether the thing exists. Casey would answer
  // 200 here and correctly -- they are a viewer on Northwind, and a viewer may
  // download.
  await signIn(page, DANA);
  const refused = await page.request.get(href!);
  expect(refused.status()).toBe(404);
});

test("a file is removed with Undo rather than a confirmation", async ({
  page,
}) => {
  await signIn(page, ALEX);
  await openTimeline(page, NORTHWIND);
  const card = await attach(page, PROPOSAL, {
    name: "draft.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("first draft of the pricing\n"),
  });
  await expect(card.getByRole("link", { name: "draft.txt" })).toBeVisible();

  await card
    .locator(".attachment-row")
    .filter({ hasText: "draft.txt" })
    .getByRole("button", { name: "Delete" })
    .click();

  await expect(card.getByRole("link", { name: "draft.txt" })).toHaveCount(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(card.getByRole("link", { name: "draft.txt" })).toBeVisible();
});
