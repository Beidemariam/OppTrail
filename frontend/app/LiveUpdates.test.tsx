import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { aNote, anEntry, anOpportunity, BLAIR } from "./test-api";
import {
  backToBoard,
  openTimeline,
  renderDashboard,
  renderDeal,
} from "./test-app";
import { stubEventSource } from "./test-live-updates";
import { writeInEditor } from "./test-editor";

/**
 * The client half of ADR 0003 (milestone 3.4): what an open timeline does
 * when the server says somebody else wrote something.
 *
 * The mapping from event to query keys is `lib/liveUpdates.test.ts`; what is
 * checked here is the thing a reader would notice — the screen catches up
 * without a refresh — and the two rules that are easy to get wrong: the
 * connection is opened for the opportunity on screen and closed when the
 * reader leaves, and the first `ready` does not provoke a refetch of data the
 * screen has only just loaded.
 */

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("catches the timeline up when a colleague writes to this opportunity", async () => {
  const streams = stubEventSource();
  const api = await renderDashboard({
    opportunities: [anOpportunity()],
    entries: [anEntry()],
  });

  await openTimeline("Northwind rollout");
  await screen.findByRole("heading", { name: "Discovery call" });

  await waitFor(() => expect(streams).toHaveLength(1));
  expect(streams[0].url).toBe("/api/v2/opportunities/10/events");

  // The colleague's write, which this reader's client knows nothing about.
  api.entries.push(anEntry({ id: 101, title: "Legal sent redlines" }));
  expect(screen.queryByRole("heading", { name: "Legal sent redlines" })).toBe(
    null,
  );

  act(() => streams[0].emit("timeline.changed"));

  expect(
    await screen.findByRole("heading", { name: "Legal sent redlines" }),
  ).toBeInTheDocument();
});

it("does not refetch on the first ready", async () => {
  const streams = stubEventSource();
  const api = await renderDashboard({
    opportunities: [anOpportunity()],
    entries: [anEntry()],
  });

  await openTimeline("Northwind rollout");
  await screen.findByRole("heading", { name: "Discovery call" });
  await waitFor(() => expect(streams).toHaveLength(1));

  const before = api.calls.length;
  act(() => streams[0].emit("ready"));
  await Promise.resolve();

  // The screen has only just read everything this event would invalidate.
  // A reconnect is different — that one is a gap, and does refetch.
  expect(api.calls).toHaveLength(before);
});

it("refetches after a reconnect, because a closed stream is a gap", async () => {
  const streams = stubEventSource();
  const api = await renderDashboard({
    opportunities: [anOpportunity()],
    entries: [anEntry()],
  });

  await openTimeline("Northwind rollout");
  await screen.findByRole("heading", { name: "Discovery call" });
  await waitFor(() => expect(streams).toHaveLength(1));

  act(() => streams[0].emit("ready"));
  api.entries.push(anEntry({ id: 102, title: "Written while disconnected" }));
  act(() => streams[0].emit("ready"));

  expect(
    await screen.findByRole("heading", { name: "Written while disconnected" }),
  ).toBeInTheDocument();
});

it("follows the reader from one opportunity to the next", async () => {
  // One stream per opportunity, and the old one goes when the panel does:
  // a connection left open on a deal nobody is looking at holds a worker slot
  // for nothing (ADR 0003's consequences).
  const streams = stubEventSource();
  await renderDeal({
    opportunities: [
      anOpportunity(),
      anOpportunity({ id: 11, name: "Initech" }),
    ],
    entries: [anEntry()],
  });

  await screen.findByRole("heading", { name: "Discovery call" });
  await waitFor(() => expect(streams).toHaveLength(1));

  // By way of the board, since a deal is its own page (R.1, decision 1A).
  await backToBoard();
  await openTimeline("Initech");

  await waitFor(() => expect(streams).toHaveLength(2));
  expect(streams[0].closed).toBe(true);
  expect(streams[1].url).toBe("/api/v2/opportunities/11/events");
  expect(streams[1].closed).toBe(false);
});

it("refuses a note edit written against a copy somebody else has moved", async () => {
  // The other half of ADR 0003. The fake enforces the guard the way the
  // server does (`app/test-api.ts`), so this walks the real path: the reader
  // opens the editor, the note moves underneath, and the save is refused
  // rather than overwriting text they never saw.
  const streams = stubEventSource();
  const api = await renderDashboard({
    opportunities: [anOpportunity()],
    entries: [anEntry({ notes: [aNote()] })],
  });

  await openTimeline("Northwind rollout");
  const block = (await screen.findByText("Budget holder is the COO.")).closest(
    "section",
  )!;
  await userEvent.click(within(block).getByRole("button", { name: "Edit" }));

  // Blair saves. The stream tells this client, which refetches the timeline
  // under the open editor -- so the draft survives but the note it was opened
  // against has moved.
  const note = api.entries[0].notes[0];
  note.body = "Blair got here first.";
  note.author_name = BLAIR.name;
  note.updated_at = "2026-09-30T12:00:01Z";
  note.edited = true;
  act(() => streams[0].emit("timeline.changed"));
  await waitFor(() =>
    expect(api.callsTo("GET", "/timeline").length).toBeGreaterThan(1),
  );

  writeInEditor(
    screen.getByRole("textbox", { name: "Edit this note" }),
    "My version",
  );
  await userEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(
    await screen.findByText(/Somebody else saved this note/),
  ).toBeInTheDocument();
  // The way back is named for what it does, and the note still says what the
  // other person wrote.
  await userEvent.click(
    screen.getByRole("button", { name: "Discard my edit" }),
  );
  expect(screen.getByText("Blair got here first.")).toBeInTheDocument();
});
