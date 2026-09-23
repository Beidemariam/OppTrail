import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { anEntry, anOpportunity, BLAIR } from "./test-api";
import { openTimeline, renderDashboard } from "./test-app";

/**
 * Milestone 3.0: one activity log per opportunity.
 *
 * The merge and the per-role row set are the server's (`tests/test_activity.py`);
 * what is checked here is that the opportunity offers the log to every role
 * and that each kind of event reads as a sentence rather than as a payload.
 */

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const ACTIVITY = [
  {
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
  },
  {
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
      changed_fields: ["name", "value"],
    },
  },
  {
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
  },
];

async function openActivity() {
  await userEvent.click(screen.getByRole("button", { name: "Activity" }));
  const dialog = await screen.findByRole("dialog");
  expect(
    within(dialog).getByRole("heading", { name: "Activity log" }),
  ).toBeVisible();
  return dialog;
}

describe("the activity log", () => {
  it("reads the three mechanisms as one list of sentences", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      activity: ACTIVITY,
    });
    await openTimeline("Northwind rollout");

    const dialog = await openActivity();
    const events = await within(dialog).findAllByRole("listitem");

    expect(events).toHaveLength(3);
    expect(events[0]).toHaveTextContent(
      "Alex Northwind rollout was created for Northwind.",
    );
    expect(events[1]).toHaveTextContent(
      "Blair changed Name and Value on this opportunity",
    );
    expect(events[2]).toHaveTextContent("Alex deleted a note");
  });

  it("is offered to a reader who does not own the opportunity", async () => {
    // The History button beside it is owner-only (D-096); this one is not,
    // because the server answers an editor with the rows they may read
    // rather than refusing the request (D-101).
    await renderDashboard({
      opportunities: [
        anOpportunity({
          owner_id: BLAIR.id,
          owner_name: BLAIR.name,
          current_user_role: "editor",
        }),
      ],
      entries: [anEntry()],
      activity: [ACTIVITY[0]],
    });
    await openTimeline("Northwind rollout");

    const heading: HTMLElement = document.querySelector(".timeline-heading")!;
    expect(
      within(heading).queryByRole("button", { name: "History" }),
    ).toBeNull();

    const dialog = await openActivity();
    expect(await within(dialog).findAllByRole("listitem")).toHaveLength(1);
  });

  it("says so when nothing has happened yet", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      activity: [],
    });
    await openTimeline("Northwind rollout");

    const dialog = await openActivity();
    expect(
      await within(dialog).findByText("Nothing has happened here yet."),
    ).toBeVisible();
  });
});
