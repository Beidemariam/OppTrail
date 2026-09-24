import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { anEntry, anOpportunity, aNote, BLAIR } from "./test-api";
import { openTimeline, renderDashboard } from "./test-app";
import { writeInEditor } from "./test-editor";

/**
 * One history per opportunity (milestone 3.0, completed by 3.1c).
 *
 * The merge and the per-role row set are the server's
 * (`backend/tests/test_activity.py`); what is checked here is that the
 * opportunity offers one destination to every role, that each kind of event
 * reads as a sentence rather than as a payload, and that an edit opens to the
 * before/after and the way back that used to need a second dialog (D-121).
 */

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const SYSTEM_EVENT = {
  id: 96,
  opportunity_id: 10,
  occurred_at: "2026-09-01T09:00:00Z",
  actor_id: 1,
  actor_name: "Alex",
  detail: {
    source: "system_entry" as const,
    entry_id: 12,
    title: "Opportunity created",
    body: "Northwind rollout was created for Northwind.",
  },
};

const EDIT_EVENT = {
  id: 34,
  opportunity_id: 10,
  occurred_at: "2026-09-02T11:30:00Z",
  actor_id: 2,
  actor_name: "Blair",
  detail: {
    source: "version" as const,
    target: "opportunity" as const,
    target_id: 10,
    version_number: 2,
    changed_fields: ["value"],
  },
};

const DELETE_EVENT = {
  id: 41,
  opportunity_id: 10,
  occurred_at: "2026-09-03T08:15:00Z",
  actor_id: 1,
  actor_name: "Alex",
  detail: {
    source: "audit_log" as const,
    action: "note_deleted" as const,
    detail: { note_id: 4, entry_id: 100, author_id: 2 },
  },
};

async function openHistory() {
  await userEvent.click(screen.getByRole("button", { name: "History" }));
  const dialog = await screen.findByRole("dialog");
  expect(
    within(dialog).getByRole("heading", { name: "Activity and history" }),
  ).toBeVisible();
  return dialog;
}

/** Edits the value from the heading, which is what gives the fake a version 1
 * and a version 2 for the edit row below to open onto. */
async function editValue(to: string) {
  const facts: HTMLElement = document.querySelector(".opportunity-facts")!;
  await userEvent.click(within(facts).getByTitle("Edit Value"));
  await userEvent.clear(within(facts).getByLabelText("Value"));
  await userEvent.type(within(facts).getByLabelText("Value"), to);
  await userEvent.keyboard("{Enter}");
  await waitFor(() =>
    expect(document.querySelector(".opportunity-facts")!.textContent).toContain(
      "250,000",
    ),
  );
}

describe("the activity log", () => {
  it("reads the three mechanisms as one list of sentences", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      activity: [SYSTEM_EVENT, EDIT_EVENT, DELETE_EVENT],
    });
    await openTimeline("Northwind rollout");

    const dialog = await openHistory();
    const events = await within(dialog).findAllByRole("listitem");

    expect(events).toHaveLength(3);
    expect(events[0]).toHaveTextContent(
      "Alex Northwind rollout was created for Northwind.",
    );
    expect(events[1]).toHaveTextContent(
      "Blair changed Value on this opportunity",
    );
    expect(events[2]).toHaveTextContent("Alex deleted a note");
  });

  it("opens an edit onto what it changed", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      activity: [EDIT_EVENT],
    });
    await openTimeline("Northwind rollout");
    await editValue("250000");

    const dialog = await openHistory();
    // Nothing is fetched until the reader asks: a log of forty edits would
    // otherwise open with forty requests.
    expect(within(dialog).queryByText("Value")).toBeNull();

    await userEvent.click(
      within(dialog).getByRole("button", { name: "What changed" }),
    );

    // Read through the field declarations the history screen always used, so
    // the money is still money rather than the column's raw text.
    expect(await within(dialog).findByText("USD 185,000")).toBeInTheDocument();
    expect(within(dialog).getByText("USD 250,000")).toBeInTheDocument();
  });

  it("restores the version an edit replaced", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      activity: [EDIT_EVENT],
    });
    await openTimeline("Northwind rollout");
    await editValue("250000");

    const dialog = await openHistory();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "What changed" }),
    );
    // Version 1 — the state the deal was created in — is reached as the
    // "before" of the first edit, which is how every recorded version except
    // the current one is reachable (D-120).
    await userEvent.click(
      await within(dialog).findByRole("button", { name: "Restore version 1" }),
    );

    await waitFor(() =>
      expect(
        api.callsTo("POST", "/api/v2/opportunities/10/versions/1/restore"),
      ).toHaveLength(1),
    );
    expect(await screen.findByText(/Restored version 1/)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        document.querySelector(".opportunity-facts")!.textContent,
      ).toContain("USD 185,000"),
    );
  });

  it("opens an edit to a timeline entry the same way", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      activity: [
        {
          ...EDIT_EVENT,
          detail: {
            source: "version" as const,
            target: "timeline_entry" as const,
            target_id: 100,
            version_number: 2,
            changed_fields: ["title"],
          },
        },
      ],
    });
    await openTimeline("Northwind rollout");

    const entry = (
      await screen.findByRole("heading", { name: "Discovery call" })
    ).closest("article")!;
    await userEvent.click(within(entry).getByRole("button", { name: "Edit" }));
    const title = within(entry).getByLabelText("Title");
    await userEvent.clear(title);
    await userEvent.type(title, "Discovery call, revised");
    await userEvent.click(
      within(entry).getByRole("button", { name: "Save Entry" }),
    );
    await screen.findByRole("heading", { name: "Discovery call, revised" });

    const dialog = await openHistory();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "What changed" }),
    );

    expect(await within(dialog).findByText("Title")).toBeInTheDocument();
    expect(within(dialog).getByText("Discovery call")).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Restore version 1" }),
    ).toBeInTheDocument();
  });

  it("opens an edit to a note the same way", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry({ notes: [aNote()] })],
      activity: [
        {
          ...EDIT_EVENT,
          detail: {
            source: "version" as const,
            target: "note" as const,
            target_id: 200,
            version_number: 2,
            changed_fields: ["body"],
          },
        },
      ],
    });
    await openTimeline("Northwind rollout");

    const note = (await screen.findByText("Budget holder is the COO.")).closest(
      "section",
    )!;
    await userEvent.click(within(note).getByRole("button", { name: "Edit" }));
    writeInEditor(
      within(note).getByLabelText("Edit this note"),
      "Budget holder is the CFO.",
    );
    await userEvent.click(within(note).getByRole("button", { name: "Save" }));
    await screen.findByText("Budget holder is the CFO.");

    const dialog = await openHistory();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "What changed" }),
    );

    expect(await within(dialog).findByText("Body")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Budget holder is the COO."),
    ).toBeInTheDocument();

    // And restoring a note reaches the note's own route rather than the
    // opportunity's: three histories, three paths, one control.
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Restore version 1" }),
    );
    await waitFor(() =>
      expect(
        api.callsTo("POST", "/api/v2/notes/200/versions/1/restore"),
      ).toHaveLength(1),
    );
  });

  it("is offered to a reader who does not own the opportunity", async () => {
    // The only destination since 3.1c, and open to every role: the server
    // answers an editor with the rows they may read rather than refusing the
    // request (D-101). An edit row never reaches them, so the Restore control
    // inside one needs no second permission check.
    await renderDashboard({
      opportunities: [
        anOpportunity({
          owner_id: BLAIR.id,
          owner_name: BLAIR.name,
          current_user_role: "editor",
        }),
      ],
      entries: [anEntry()],
      activity: [SYSTEM_EVENT],
    });
    await openTimeline("Northwind rollout");

    const dialog = await openHistory();
    expect(await within(dialog).findAllByRole("listitem")).toHaveLength(1);
    expect(
      within(dialog).queryByRole("button", { name: "What changed" }),
    ).toBeNull();
  });

  it("says so when nothing has happened yet", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      activity: [],
    });
    await openTimeline("Northwind rollout");

    const dialog = await openHistory();
    expect(
      await within(dialog).findByText("Nothing has happened here yet."),
    ).toBeVisible();
  });
});
