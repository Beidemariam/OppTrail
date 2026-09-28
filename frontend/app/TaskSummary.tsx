"use client";

import { Link } from "react-router";

import { taskStanding, todayIsoDate } from "../lib/domain";
import { useMyTasks } from "../lib/queries";

/**
 * What is waiting for you, on the dashboard (milestone 4.1,
 * `docs/ROADMAP.md` Phase 4: "overdue and upcoming on the dashboard").
 *
 * A count and a link, not a second task list. The list is `/tasks`, and putting
 * a copy of it on the board would be two places to read the same rows and two
 * places to keep them in sync on screen — the mistake the three History
 * destinations made (D-121). What belongs here is the one fact a rep needs
 * without leaving the board: whether anything is late.
 *
 * Renders **nothing at all** when there is nothing due. An empty panel saying
 * "no overdue tasks" is a permanent reminder of the absence of a problem, which
 * is the clutter `AGENTS.md`'s Design bar rules out.
 */
export function TaskSummary() {
  const tasks = useMyTasks();
  const today = todayIsoDate();

  const standings = (tasks.data ?? []).map((task) => taskStanding(task, today));
  const overdue = standings.filter((standing) => standing === "overdue").length;
  const dueToday = standings.filter((standing) => standing === "today").length;

  if (overdue === 0 && dueToday === 0) {
    return null;
  }

  return (
    <p className="task-summary">
      {overdue > 0 && (
        <span className="task-summary-overdue">
          {overdue} {overdue === 1 ? "task is" : "tasks are"} overdue
        </span>
      )}
      {dueToday > 0 && <span>{dueToday} due today</span>}
      <Link to="/tasks">My tasks</Link>
    </p>
  );
}
