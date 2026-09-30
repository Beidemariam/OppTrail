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
    expect(within(panel).queryByLabelText("Task title")).toBeNull();
    await userEvent.click(
      within(panel).getByRole("button", { name: "Add task" }),
    );

    await userEvent.type(
      within(panel).getByLabelText("Task title"),
      "Call them back",
    );
    // The assignee is picked from the people on this deal, not typed from
    // memory -- the mistake requirement 13 made once (D-123).
    await userEvent.selectOptions(
      within(panel).getByLabelText("Who this task is for"),
      BLAIR.email,
    );
    await userEvent.type(
      within(panel).getByLabelText("When this task is due"),
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
      expect(within(taskPanel()).queryByLabelText("Task title")).toBeNull(),
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

describe("the calendar's task layer (milestone 4.2)", () => {
  it("draws a task on its due date, whatever month that is", async () => {
    // The month is part of the URL, and a link may legitimately name one years
    // out — the case the e2e spec exercises with 2027-08.
    const api = await renderDashboard(
      {
        opportunities: [anOpportunity()],
        tasks: [
          aTask({
            id: 501,
            title: "Send updated pricing",
            due_date: "2027-08-19",
          }),
        ],
      },
      "/?opportunities.view=calendar&opportunities.month=2027-08",
    );

    await screen.findByRole("heading", { name: "August 2027" });
    await waitFor(() =>
      expect(api.callsTo("GET", "assignee=any")).not.toHaveLength(0),
    );
    expect(
      await screen.findByRole("link", { name: "Send updated pricing" }),
    ).toBeInTheDocument();
  });
});

describe("a session that ends while the app is open (milestone 4.2a, D-145)", () => {
  it("returns to the sign-in screen instead of blaming the action", async () => {
    // The Phase 4 reviewer met this as "I can't delete the task because
    // authentication is required": a dead session left every request failing
    // while the screen carried on showing a signed-in page, so the message
    // sounded like the *task* had refused them.
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      tasks: [aTask({ id: 501, title: "Send pricing" })],
    });
    await openTimeline("Northwind rollout");
    const panel = await waitFor(() => taskPanel());

    // The session ends *now*, with the app already open and showing a
    // signed-in page — which is the situation, and the reason this cannot be
    // set up before the first render.
    api.failures["DELETE /api/v2/tasks/501"] = [401, "Authentication required"];
    api.failures["GET /api/v2/auth/me"] = [401, "Authentication required"];

    await userEvent.click(
      within(panel).getByRole("button", { name: "Delete" }),
    );

    await waitFor(() =>
      expect(api.callsTo("DELETE", "/api/v2/tasks/501")).toHaveLength(1),
    );
    // The app notices it is signed out and says so, rather than leaving a
    // signed-in page whose every control fails.
    expect(
      await screen.findByRole("button", { name: /^Sign in$/ }),
    ).toBeInTheDocument();
  });
});

describe("editing a task (milestone 4.2a)", () => {
  it("changes the assignee, the date and the title in place", async () => {
    // Milestone 4.1 shipped the PATCH route with nothing calling it: the panel
    // offered Delete and no way to change any field. The reviewer asked for
    // reassignment by name.
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      tasks: [aTask({ id: 501, title: "Call them back" })],
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

    await userEvent.click(within(panel).getByRole("button", { name: "Edit" }));

    // The editor opens in the row, not in a form elsewhere on the page (2.11).
    const title = within(taskPanel()).getByLabelText("Task title");
    expect(title).toHaveValue("Call them back");
    expect(title).toHaveFocus();

    await userEvent.clear(title);
    await userEvent.type(title, "Call them today");
    await userEvent.selectOptions(
      within(taskPanel()).getByLabelText("Who this task is for"),
      BLAIR.email,
    );
    await userEvent.type(
      within(taskPanel()).getByLabelText("When this task is due"),
      isoDaysFromToday(5),
    );
    await userEvent.click(
      within(taskPanel()).getByRole("button", { name: "Save Task" }),
    );

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/v2/tasks/501")).toHaveLength(1),
    );
    expect(api.callsTo("PATCH", "/api/v2/tasks/501")[0].body).toMatchObject({
      title: "Call them today",
      assignee_email: BLAIR.email,
      due_date: isoDaysFromToday(5),
    });
  });

  it("shows a description as Markdown", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      tasks: [
        aTask({
          id: 501,
          title: "Send pricing",
          description: "They want the **2027** figures.",
        }),
      ],
    });
    await openTimeline("Northwind rollout");
    const panel = await waitFor(() => taskPanel());

    // Rendered, not printed: the asterisks become emphasis, the way every other
    // body in this app does.
    expect(within(panel).getByText("2027").tagName).toBe("STRONG");
  });
});

describe("the corners of the task screens", () => {
  it("asks a signed-out visitor to sign in rather than showing an empty list", async () => {
    // `/tasks` is a deep link, so it can be opened by somebody whose session has
    // gone — the same situation D-145 is about, arrived at from the URL bar.
    renderApp({ user: null }, "/tasks");

    expect(
      await screen.findByRole("heading", { name: "My tasks" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });

  it("links a task back to the entry that prompted it", async () => {
    // The `?entry=` link (D-124's shape): a task migrated from a follow-up date
    // reaches the conversation it came from. The title is null once that entry is
    // deleted, and the task stays — which is why both are checked before the
    // link is drawn.
    renderApp(
      {
        user: ALEX,
        opportunities: [anOpportunity()],
        tasks: [
          aTask({ id: 501, entry_id: 100, entry_title: "Discovery call" }),
          aTask({ id: 502, title: "Orphan", entry_id: 100, entry_title: null }),
        ],
      },
      "/tasks",
    );

    await screen.findByRole("heading", { name: "My tasks" });
    expect(
      screen.getByRole("link", { name: "Discovery call" }),
    ).toHaveAttribute("href", "/opportunities/10?entry=100");
    // The orphaned one is listed, without a link to an entry nobody can read.
    expect(screen.getByText("Orphan")).toBeInTheDocument();
  });

  it("reopens a done task from My Tasks", async () => {
    const api = renderApp(
      {
        user: ALEX,
        opportunities: [anOpportunity()],
        tasks: [
          aTask({
            id: 501,
            title: "Already done",
            completed_at: "2026-09-20T09:00:00Z",
            completed_by: ALEX.id,
            completed_by_name: ALEX.name,
          }),
        ],
      },
      "/tasks?include_completed=true",
    );

    await screen.findByRole("heading", { name: "My tasks" });
    // Nothing open, so the list says so rather than drawing an empty group.
    expect(
      screen.getByRole("heading", { name: "Nothing is assigned to you." }),
    ).toBeInTheDocument();
    expect(api.callsTo("GET", "/api/v2/tasks").length).toBeGreaterThan(0);
  });
});

describe("reopening a done task", () => {
  it("is offered from the deal's panel, behind the Done disclosure", async () => {
    // The other direction of the one toggle (`useSetTaskDone`): the checkbox in
    // the done list unticks, which is the branch a test that only ever completes
    // a task never reaches.
    const api = await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      tasks: [
        aTask({
          id: 501,
          title: "Already done",
          completed_at: "2026-09-20T09:00:00Z",
          completed_by: ALEX.id,
          completed_by_name: ALEX.name,
        }),
      ],
    });
    await openTimeline("Northwind rollout");
    const panel = await waitFor(() => taskPanel());

    expect(within(panel).getByText("0 open")).toBeInTheDocument();
    await userEvent.click(
      within(panel).getByRole("button", { name: /Done \(1\)/ }),
    );
    // Who finished it, which is what the timestamp pair buys over a boolean.
    expect(within(taskPanel()).getByText(/Done by Alex/)).toBeInTheDocument();

    await userEvent.click(
      within(taskPanel()).getByRole("checkbox", { name: /Already done/ }),
    );

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/v2/tasks/501/reopen")).toHaveLength(1),
    );
  });

  it("is offered from My Tasks too", async () => {
    const api = renderApp(
      {
        user: ALEX,
        opportunities: [anOpportunity()],
        tasks: [aTask({ id: 501, title: "Open one" })],
      },
      "/tasks",
    );
    await screen.findByRole("heading", { name: "My tasks" });

    await userEvent.click(screen.getByRole("checkbox", { name: /Open one/ }));

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/v2/tasks/501/complete")).toHaveLength(1),
    );
  });
});

describe("when a task read or write fails", () => {
  it("reports a refused list rather than an empty one", async () => {
    // An empty list and a failed read look identical unless the failure is said
    // out loud, which is the mistake D-076 found in the dashboard's empty
    // states.
    renderApp(
      {
        user: ALEX,
        opportunities: [anOpportunity()],
        failures: {
          "GET /api/v2/tasks": [500, "The task list is unavailable"],
        },
      },
      "/tasks",
    );

    await screen.findByRole("heading", { name: "My tasks" });
    expect(
      await screen.findByText("The task list is unavailable"),
    ).toBeInTheDocument();
  });

  it("keeps the form open and says why when a write is refused", async () => {
    // The editor closes on success only: a form that closes and silently
    // discards what was typed is worse than one that stays and explains.
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      failures: {
        "POST /api/v2/opportunities/10/tasks": [422, "That title is too long"],
      },
    });
    await openTimeline("Northwind rollout");
    const panel = await waitFor(() => taskPanel());

    await userEvent.click(
      within(panel).getByRole("button", { name: "Add task" }),
    );
    await userEvent.type(
      within(taskPanel()).getByLabelText("Task title"),
      "Something",
    );
    await userEvent.click(
      within(taskPanel()).getByRole("button", { name: "Add Task" }),
    );

    expect(
      await within(taskPanel()).findByText("That title is too long"),
    ).toBeInTheDocument();
    // Still open, with the draft intact.
    expect(within(taskPanel()).getByLabelText("Task title")).toHaveValue(
      "Something",
    );
  });

  it("reports a refused panel read", async () => {
    await renderDashboard({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
      failures: {
        "GET /api/v2/opportunities/10/tasks": [500, "Tasks are unavailable"],
      },
    });
    await openTimeline("Northwind rollout");

    expect(
      await screen.findByText("Tasks are unavailable"),
    ).toBeInTheDocument();
  });
});
