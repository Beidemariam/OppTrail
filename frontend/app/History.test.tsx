import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { aNote, anEntry, anOpportunity, BLAIR } from "./test-api";
import { findCard, openTimeline, renderDashboard } from "./test-app";
import { versionChanges, opportunityVersionFields } from "../lib/domain";

/**
 * Milestone 2.10: every edit keeps what it replaced, and one screen shows it
 * for all three editable things.
 *
 * The fake API writes the versions itself when it handles a write
 * (`app/test-api.ts`), so these drive the edit through the UI and then read
 * the history the edit produced, rather than asserting against a canned list
 * that would pass with no versioning behind it.
 */

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/**
 * Opens one History button and returns the dialog it raised.
 *
 * Scoped to the element that owns the button, because a timeline shows the
 * opportunity's history beside the exports and one per entry and note below
 * it — all with the same label, which is the point: the control means the
 * same thing wherever it is.
 */
async function openHistory(scope: HTMLElement, title: string) {
  await userEvent.click(within(scope).getByRole("button", { name: "History" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByRole("heading", { name: title })).toBeVisible();
  return dialog;
}

/** The opportunity's own header, which carries its history button. */
function heading(): HTMLElement {
  return document.querySelector(".timeline-heading")!;
}

/** One timeline entry card, by the title it currently shows. */
async function entryCard(title: string): Promise<HTMLElement> {
  const cards = await screen.findAllByRole("article");
  return cards.find((candidate) => candidate.textContent?.includes(title))!;
}

/** The first note block on screen. */
function noteBlock(): HTMLElement {
  return document.querySelector("section.note-block")!;
}

describe("edit history", () => {
  it("shows what an opportunity's value used to be", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    // The edit the history is about to be read for, made where a reader makes
    // it: the create/edit dialog on the card (D-079).
    const card = await findCard("Northwind rollout");
    await userEvent.click(within(card).getByRole("button", { name: "Edit" }));
    const form = await screen.findByRole("dialog");
    const value = within(form).getByLabelText("Value");
    await userEvent.clear(value);
    await userEvent.type(value, "162000");
    await userEvent.click(
      within(form).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const dialog = await openHistory(heading(), "History of Northwind rollout");

    const versions = within(dialog).getAllByRole("listitem");
    expect(versions).toHaveLength(2);
    // Version 1 is the whole state the deal was created in; version 2 is the
    // one field that moved, with the figure it replaced still readable.
    expect(versions[0]).toHaveTextContent("Version 1");
    expect(versions[0]).toHaveTextContent("USD 185,000");
    expect(versions[1]).toHaveTextContent("Version 2");
    expect(versions[1]).toHaveTextContent("USD 185,000 to USD 162,000");
  });

  it("shows a timeline entry's previous title, and only the fields that moved", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    const entry = await entryCard("Discovery call");
    await userEvent.click(within(entry).getByRole("button", { name: "Edit" }));
    // Scoped to the entry: since milestone 2.11 the editor is inside the card
    // and the composer at the top of the panel has a Title field of its own.
    const title = within(entry).getByLabelText("Title");
    await userEvent.clear(title);
    await userEvent.type(title, "Discovery call, corrected");
    await userEvent.click(
      within(entry).getByRole("button", { name: "Save Entry" }),
    );
    await screen.findByRole("heading", { name: "Discovery call, corrected" });

    const dialog = await openHistory(
      await entryCard("Discovery call, corrected"),
      "History of this timeline entry",
    );

    const versions = within(dialog).getAllByRole("listitem");
    expect(versions[0]).toHaveTextContent("Discovery call");
    expect(versions[1]).toHaveTextContent(
      "Discovery call to Discovery call, corrected",
    );
    // The second version lists Title alone: nothing else changed, and the
    // first version is where the rest is already written down.
    expect(
      within(versions[1])
        .getAllByRole("term")
        .map((term) => term.textContent),
    ).toEqual(["Title"]);
  });

  it("shows a note's previous text after an edit", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote()] })],
    });
    await openTimeline("Northwind rollout");

    const note = noteBlock();
    await userEvent.click(within(note).getByRole("button", { name: "Edit" }));
    const textarea = screen.getByLabelText("Edit this note");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "Budget holder is the CFO.");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Budget holder is the CFO.");

    const dialog = await openHistory(noteBlock(), "History of this note");

    const versions = within(dialog).getAllByRole("listitem");
    expect(versions[0]).toHaveTextContent("Budget holder is the COO.");
    expect(versions[1]).toHaveTextContent(
      "Budget holder is the COO. to Budget holder is the CFO.",
    );
  });

  it("says when a save changed nothing, rather than drawing a gap", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    const card = await findCard("Northwind rollout");
    await userEvent.click(within(card).getByRole("button", { name: "Edit" }));
    const form = await screen.findByRole("dialog");
    await userEvent.click(
      within(form).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const dialog = await openHistory(heading(), "History of Northwind rollout");

    expect(
      within(dialog).getByText("Saved with no field changed."),
    ).toBeInTheDocument();
  });

  it("reports a history that cannot be read", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      failures: {
        "GET /api/v2/opportunities/10/versions": [500, "History unavailable"],
      },
    });
    await openTimeline("Northwind rollout");

    const dialog = await openHistory(heading(), "History of Northwind rollout");

    expect(
      await within(dialog).findByText("History unavailable"),
    ).toBeInTheDocument();
  });

  it("says it is loading while the history is in flight", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      pending: ["GET /api/v2/opportunities/10/versions"],
    });
    await openTimeline("Northwind rollout");

    const dialog = await openHistory(heading(), "History of Northwind rollout");
    expect(within(dialog).getByText("Loading history...")).toBeInTheDocument();

    api.release("GET /api/v2/opportunities/10/versions");
    expect(
      await within(dialog).findByText("No history recorded for this item."),
    ).toBeInTheDocument();
  });

  it("offers no history to an editor, who may still write", async () => {
    await renderDashboard({
      user: BLAIR,
      opportunities: [anOpportunity({ current_user_role: "editor" })],
      entries: [anEntry({ created_by: BLAIR.id, author_name: BLAIR.name })],
    });
    await openTimeline("Northwind rollout");

    expect(await screen.findByPlaceholderText("Add note")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "History" })).toBeNull();
  });

  it("says so when nothing has been recorded yet", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    const dialog = await openHistory(heading(), "History of Northwind rollout");

    expect(
      within(dialog).getByText("No history recorded for this item."),
    ).toBeInTheDocument();
  });
});

describe("versionChanges", () => {
  const base = {
    id: 1,
    opportunity_id: 10,
    version_number: 1,
    name: "Northwind rollout",
    account_name: "Northwind",
    value: "185000",
    currency: "USD",
    stage: "Negotiation" as const,
    expected_close_date: "2026-12-01",
    edited_by: 1,
    editor_name: "Alex",
    created_at: "2026-09-01T09:00:00Z",
  };

  it("reads the first version as the whole state", () => {
    expect(
      versionChanges(opportunityVersionFields, base, undefined).map(
        (change) => [change.label, change.before, change.after],
      ),
    ).toEqual([
      ["Name", null, "Northwind rollout"],
      ["Account", null, "Northwind"],
      ["Value", null, "USD 185,000"],
      ["Stage", null, "Negotiation"],
      ["Close date", null, "2026-12-01"],
    ]);
  });

  it("reads a later version as only what it moved", () => {
    const next = { ...base, version_number: 2, value: "162000" };

    expect(versionChanges(opportunityVersionFields, next, base)).toEqual([
      { label: "Value", before: "USD 185,000", after: "USD 162,000" },
    ]);
  });

  it("reads a save that changed nothing as nothing", () => {
    expect(versionChanges(opportunityVersionFields, { ...base }, base)).toEqual(
      [],
    );
  });
});
