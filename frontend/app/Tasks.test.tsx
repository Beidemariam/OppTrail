import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ALEX, BLAIR, aTask, anEntry, anOpportunity } from "./test-api";
import { openTimeline, renderApp, renderDashboard } from "./test-app";

/**
 * Tasks on screen (milestone 4.1): the panel on a deal, My Tasks across deals,
 * and the one line the dashboard carries.
 *
 * Dates are built relative to today, never hardcoded: "overdue" is a question
 * about the wall clock, and `AGENTS.md`'s quality bar forbids an assertion that
 * depends on it.
 */

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function isoDaysFromToday(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function taskPanel() {
  return document.querySelector(".task-panel") as HTMLElement;
}

describe("a deal's task panel", () => {
  it("lists what is outstanding and counts it", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      tasks: [
        aTask({ id: 501, title: "Send pricing" }),
        aTask({ id: 502, title: "Book the demo" }),
      ],
    });
    await openTimeline("Northwind rollout");

    const panel = await waitFor(() => taskPanel());
    expect(within(panel).getByText("Send pricing")).toBeInTheDocument();
    expect(within(panel).getByText("2 open")).toBeInTheDocument();
  });

  it("writes a task down, for a colleague, due on a date", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      shares: [
        {
          user_id: BLAIR.id,
          email: BLAIR.email,
          name: BLAIR.name,
          role: "editor",
          created_at: "2026-09-01T00:00:00Z",
          invited_by: ALEX.id,
          invited_by_name: ALEX.name,
        },
      ],
    });
    await openTimeline("Northwind rollout");
    const panel = await waitFor(() => taskPanel());

    // Collapsed until asked for, like every other composer since 3.7.
    expect(within(panel).queryByLabelText("Task")).toBeNull();
    await userEvent.click(
      within(panel).getByRole("button", { name: "Add task" }),
    );

    await userEvent.type(
      within(panel).getByLabelText("Task"),
      "Call them back",
    );
    // The assignee is picked from the people on this deal, not typed from
    // memory -- the mistake requirement 13 made once (D-123).
    await userEvent.selectOptions(
      within(panel).getByLabelText("For"),
      BLAIR.email,
    );
    await userEvent.type(
      within(panel).getByLabelText("Due"),
      isoDaysFromToday(3),
    );
    await userEvent.click(
      within(panel).getByRole("button", { name: "Add Task" }),
    );

    await waitFor(() => expect(api.callsTo("POST", "/tasks")).toHaveLength(1));
    expect(api.callsTo("POST", "/tasks")[0].body).toMatchObject({
      title: "Call them back",
      assignee_email: BLAIR.email,
      due_date: isoDaysFromToday(3),
    });
    // Posting closes the composer, the way posting a note unmounts its editor.
    await waitFor(() =>
      expect(within(taskPanel()).queryByLabelText("Task")).toBeNull(),
    );
  });

  it("ticks a task off and shows who did it", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      tasks: [aTask({ id: 501, title: "Send pricing" })],
    });
    await openTimeline("Northwind rollout");
    const panel = await waitFor(() => taskPanel());

    await userEvent.click(
      within(panel).getByRole("checkbox", { name: /Send pricing/ }),
    );

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/v2/tasks/501/complete")).toHaveLength(1),
    );
    // It leaves the open list and is readable behind the disclosure, because
    // "we already did that" is what a shared record is for.
    await waitFor(() =>
      expect(within(taskPanel()).getByText("0 open")).toBeInTheDocument(),
    );
    await userEvent.click(
      within(taskPanel()).getByRole("button", { name: /Done \(1\)/ }),
    );
    expect(within(taskPanel()).getByText("Send pricing")).toBeInTheDocument();
  });

  it("deletes a task with an Undo rather than a confirmation", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      tasks: [aTask({ id: 501, title: "Send pricing" })],
    });
    await openTimeline("Northwind rollout");
    const panel = await waitFor(() => taskPanel());

    await userEvent.click(
      within(panel).getByRole("button", { name: "Delete" }),
    );

    await waitFor(() =>
      expect(api.callsTo("DELETE", "/api/v2/tasks/501")).toHaveLength(1),
    );
    expect(screen.queryByRole("alertdialog")).toBeNull();

    const toast = await screen.findByText("Task deleted.");
    await userEvent.click(
      within(toast.closest(".toast") as HTMLElement).getByRole("button", {
        name: "Undo",
      }),
    );

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/v2/tasks/501/restore")).toHaveLength(1),
    );
    await waitFor(() =>
      expect(within(taskPanel()).getByText("Send pricing")).toBeInTheDocument(),
    );
  });

  it("offers a viewer no way to write or change one", async () => {
    await renderDashboard({
      opportunities: [anOpportunity({ current_user_role: "viewer" })],
      entries: [anEntry()],
      tasks: [aTask({ id: 501, created_by: BLAIR.id, assignee_id: BLAIR.id })],
    });
    await openTimeline("Northwind rollout");
    const panel = await waitFor(() => taskPanel());

    expect(
      within(panel).queryByRole("button", { name: "Add task" }),
    ).toBeNull();
    expect(within(panel).queryByRole("button", { name: "Delete" })).toBeNull();
  });
});

describe("my tasks", () => {
  it("groups by standing, newest problem first, across deals", async () => {
    renderApp(
      {
        user: ALEX,
        opportunities: [anOpportunity()],
        tasks: [
          aTask({
            id: 501,
            title: "Late thing",
            due_date: isoDaysFromToday(-3),
          }),
          aTask({
            id: 502,
            title: "Today thing",
            due_date: isoDaysFromToday(0),
          }),
          aTask({
            id: 503,
            title: "Soon thing",
            due_date: isoDaysFromToday(5),
          }),
          aTask({ id: 504, title: "Someday thing", due_date: null }),
        ],
      },
      "/tasks",
    );

    await screen.findByRole("heading", { name: "My tasks" });
    const headings = screen
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);
    expect(headings).toEqual(["Overdue", "Due today", "Coming up", "No date"]);

    // The deal's name is a link, because a task read away from its opportunity
    // is not actionable without one.
    expect(
      screen.getAllByRole("link", { name: "Northwind rollout" }).length,
    ).toBeGreaterThan(0);
  });

  it("says so when nothing is assigned", async () => {
    renderApp(
      { user: ALEX, opportunities: [anOpportunity()], tasks: [] },
      "/tasks",
    );

    expect(
      await screen.findByRole("heading", {
        name: "Nothing is assigned to you.",
      }),
    ).toBeInTheDocument();
  });

  it("shows only what is assigned to the reader", async () => {
    renderApp(
      {
        user: ALEX,
        opportunities: [anOpportunity()],
        tasks: [
          aTask({ id: 501, title: "Mine", assignee_id: ALEX.id }),
          aTask({ id: 502, title: "Blair's", assignee_id: BLAIR.id }),
        ],
      },
      "/tasks",
    );

    await screen.findByRole("heading", { name: "My tasks" });
    expect(screen.getByText("Mine")).toBeInTheDocument();
    expect(screen.queryByText("Blair's")).toBeNull();
  });

  it("is reached with g then t", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });

    await userEvent.keyboard("gt");

    expect(
      await screen.findByRole("heading", { name: "My tasks" }),
    ).toBeInTheDocument();
  });
});

describe("the dashboard's line about what is waiting", () => {
  it("counts what is overdue and due today, and links to the list", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      tasks: [
        aTask({ id: 501, due_date: isoDaysFromToday(-1) }),
        aTask({ id: 502, due_date: isoDaysFromToday(-4) }),
        aTask({ id: 503, due_date: isoDaysFromToday(0) }),
      ],
    });

    expect(await screen.findByText("2 tasks are overdue")).toBeInTheDocument();
    expect(screen.getByText("1 due today")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "My tasks" })).toBeInTheDocument();
  });

  it("renders nothing when nothing is due", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      tasks: [aTask({ id: 501, due_date: isoDaysFromToday(9) })],
    });

    await screen.findByRole("heading", { name: "Opportunities" });
    // An empty panel saying "no overdue tasks" is a permanent reminder that
    // there is no problem, which the Design bar rules out.
    expect(document.querySelector(".task-summary")).toBeNull();
  });
});
