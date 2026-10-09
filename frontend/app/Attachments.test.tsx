import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ALEX, BLAIR, anAttachment, anEntry, anOpportunity } from "./test-api";
import { openTimeline, renderDashboard } from "./test-app";

/**
 * Attachments on a timeline entry, from the reader's side (milestone 4.3).
 *
 * The rules being checked are the backend's — a viewer may download and may
 * not attach, removing one is the uploader's or the owner's (D-005) — and what
 * this file proves is that the screen offers exactly the actions the API would
 * accept, plus the two things only the client decides: the size as a person
 * reads it, and Undo in place of a confirmation.
 */

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function openEntryWith(
  attachments: ReturnType<typeof anAttachment>[],
  role: "owner" | "editor" | "viewer" = "owner",
  failures: Record<string, [number, string]> = {},
) {
  const api = await renderDashboard({
    opportunities: [anOpportunity({ current_user_role: role })],
    entries: [anEntry({ attachments })],
    failures,
  });
  await openTimeline("Northwind rollout");
  await screen.findByText("Discovery call");
  return api;
}

function attachmentRow(filename: string) {
  return screen.getByText(filename).closest(".attachment-row") as HTMLElement;
}

it("reads a file as a name, a size and whoever put it there", async () => {
  await openEntryWith([anAttachment()]);

  const row = attachmentRow("proposal.pdf");
  // The API sends `byte_size` and never a formatted string, so this is the
  // client's own conversion (`formatBytes`): 2,411,724 bytes is "2.3 MB".
  expect(within(row).getByText(/2\.3 MB/)).toBeInTheDocument();
  expect(within(row).getByText(new RegExp(ALEX.name))).toBeInTheDocument();
  expect(
    within(row).getByRole("link", { name: "proposal.pdf" }),
  ).toHaveAttribute("href", "/api/v2/attachments/700/download");
});

it("downloads through the API rather than from a static path", async () => {
  await openEntryWith([anAttachment()]);

  const link = within(attachmentRow("proposal.pdf")).getByRole("link", {
    name: "proposal.pdf",
  });

  // ADR 0008: `/data` is never a static path, so the only href that can
  // appear here is the authorized route. The `download` attribute is what
  // makes a middle-click save rather than navigate.
  expect(link).toHaveAttribute("download");
  expect(link.getAttribute("href")).toMatch(
    /^\/api\/v2\/attachments\/\d+\/download$/,
  );
});

it("attaches a file behind a disclosure, and sends it as multipart", async () => {
  const api = await openEntryWith([]);

  await userEvent.click(screen.getByRole("button", { name: /Attach file/ }));
  const input = screen.getByLabelText("Choose a file");
  await userEvent.upload(
    input,
    new File(["%PDF-1.7 contract"], "contract.pdf", {
      type: "application/pdf",
    }),
  );

  await waitFor(() =>
    expect(screen.getByText("contract.pdf")).toBeInTheDocument(),
  );
  // The request the real wrapper sends is `FormData`, which is what the
  // fake records here (`test-api.ts`): a JSON body would have been a
  // different request and the server's parser would find no file.
  expect(api.calls).toContainEqual({
    method: "POST",
    path: "/api/v2/timeline/100/attachments",
    body: { file: "contract.pdf" },
  });
  // The picker closes once the file is away, so the card goes back to being
  // a card (the trigger's own job, 3.7's shape).
  expect(
    screen.getByRole("button", { name: /Attach file/ }),
  ).toBeInTheDocument();
});

it("says why the server refused a file", async () => {
  await openEntryWith([], "owner", {
    "POST /api/v2/timeline/100/attachments": [415, "Unsupported file type"],
  });

  await userEvent.click(screen.getByRole("button", { name: /Attach file/ }));
  await userEvent.upload(
    screen.getByLabelText("Choose a file"),
    new File(["MZ"], "setup.pdf", { type: "application/pdf" }),
  );

  // The allowlist is the server's and the sniffed bytes are what decide, so
  // this sentence is the API's own rather than a guess made here.
  expect(await screen.findByText("Unsupported file type")).toBeInTheDocument();
});

it("deletes without confirming, and offers the way back", async () => {
  await openEntryWith([anAttachment()]);

  await userEvent.click(
    within(attachmentRow("proposal.pdf")).getByRole("button", {
      name: "Delete",
    }),
  );

  // Optimistic: the row goes before the server answers, because the cache
  // already holds it (2.4b).
  await waitFor(() =>
    expect(screen.queryByText("proposal.pdf")).not.toBeInTheDocument(),
  );
  await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
  expect(await screen.findByText("proposal.pdf")).toBeInTheDocument();
});

it("offers a viewer the download and nothing else", async () => {
  await openEntryWith([anAttachment()], "viewer");

  expect(
    within(attachmentRow("proposal.pdf")).getByRole("link", {
      name: "proposal.pdf",
    }),
  ).toBeInTheDocument();
  expect(
    within(attachmentRow("proposal.pdf")).queryByRole("button", {
      name: "Delete",
    }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Attach file/ }),
  ).not.toBeInTheDocument();
});

it("does not offer an editor the removal of a colleague's file", async () => {
  // D-005's rule, which the client mirrors so a button never offers what the
  // API would refuse: this file was uploaded by somebody else.
  await openEntryWith([anAttachment({ uploaded_by: BLAIR.id })], "editor");

  expect(
    within(attachmentRow("proposal.pdf")).queryByRole("button", {
      name: "Delete",
    }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /Attach file/ }),
  ).toBeInTheDocument();
});

it("attaches from the composer, where a person is already writing", async () => {
  // Milestone 4.3a. 4.3 put the control on the posted card only; the reviewer
  // looked in the form twice and found nothing, which is where a proposal is
  // actually to hand. The entry has to exist first, so this is two requests in
  // order rather than one carrying both.
  const api = await renderDashboard({
    opportunities: [anOpportunity()],
    entries: [anEntry()],
  });
  await openTimeline("Northwind rollout");
  await userEvent.click(
    await screen.findByRole("button", { name: "New entry" }),
  );
  await userEvent.type(screen.getByLabelText("Title"), "Proposal sent");
  await userEvent.upload(
    screen.getByLabelText("Attach a file (optional)"),
    new File(["%PDF-1.7 proposal"], "proposal.pdf", {
      type: "application/pdf",
    }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Add Entry" }));

  await waitFor(() =>
    expect(
      api.calls.filter((call) => call.path.endsWith("/attachments")),
    ).toHaveLength(1),
  );
  const posts = api.calls.filter((call) => call.method === "POST");
  const entryPost = posts.findIndex((call) => call.path.endsWith("/timeline"));
  const filePost = posts.findIndex((call) =>
    call.path.endsWith("/attachments"),
  );
  expect(entryPost).toBeGreaterThanOrEqual(0);
  // Order is the point: the file is posted at the entry the save just created.
  expect(filePost).toBeGreaterThan(entryPost);
  expect(posts[filePost].path).toMatch(
    /^\/api\/v2\/timeline\/\d+\/attachments$/,
  );
  // Not the entry that was already on the timeline: the file went to the one
  // this save just created.
  expect(posts[filePost].path).not.toContain("/timeline/100/");
});

it("keeps the entry when the file is refused, and says which one failed", async () => {
  // The entry is already saved by the time a refused file is known about, so
  // reporting "the entry failed" would be false. The form stays open with the
  // draft and the file's own reason. Driven through Edit rather than New, so
  // the entry id is the seeded one and the refusal can be aimed at it.
  await renderDashboard({
    opportunities: [anOpportunity()],
    entries: [anEntry()],
    failures: {
      "POST /api/v2/timeline/100/attachments": [415, "Unsupported file type"],
    },
  });
  await openTimeline("Northwind rollout");
  // Two controls are called Edit on this screen -- the opportunity's own and
  // the entry's -- so the entry card is the scope.
  const card = (await screen.findByText("Discovery call")).closest(
    "article.timeline-entry",
  ) as HTMLElement;
  await userEvent.click(within(card).getByRole("button", { name: "Edit" }));
  await userEvent.upload(
    screen.getByLabelText("Attach a file (optional)"),
    new File(["MZ"], "setup.pdf", { type: "application/pdf" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Save Entry" }));

  expect(
    await screen.findByText(/The entry was saved\. The file was not attached/),
  ).toBeInTheDocument();
  // The editor is still open, which is what makes a retry possible.
  expect(screen.getByLabelText("Title")).toHaveValue("Discovery call");
});

it("offers no attach trigger on a system entry", async () => {
  // A system entry is history rather than content -- it carries no Edit or
  // Delete either, and a contract hanging off "Opportunity created" is not
  // what an attachment is for.
  await renderDashboard({
    opportunities: [anOpportunity()],
    entries: [
      anEntry({ system_generated: true, title: "Opportunity created" }),
    ],
  });
  await openTimeline("Northwind rollout");
  await screen.findByText("Opportunity created");

  expect(
    screen.queryByRole("button", { name: /Attach file/ }),
  ).not.toBeInTheDocument();
});

it("draws nothing at all on an entry with no files a reader cannot add to", async () => {
  // The Design bar: a heading announcing the absence of documents is clutter,
  // the same reason `TaskSummary` renders nothing when nothing is due.
  await openEntryWith([], "viewer");

  expect(document.querySelector(".attachment-list")).toBeNull();
});

it("exports in the order the timeline is being read in", async () => {
  // Milestone 4.4b, from the human's note on check T6: the export ran
  // oldest-first whatever the screen was set to. The link carries the
  // reader's own order now, so the document matches the screen it came from.
  await renderDashboard({
    opportunities: [anOpportunity()],
    entries: [anEntry()],
  });
  await openTimeline("Northwind rollout");

  const link = await screen.findByRole("link", { name: /Export/ });
  expect(link).toHaveAttribute(
    "href",
    "/api/v2/opportunities/10/export/pdf?order=desc",
  );
});
