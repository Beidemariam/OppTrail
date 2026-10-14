"use client";

import {
  taskStanding,
  todayIsoDate,
  type Task,
  type TaskStanding,
} from "../lib/domain";
import { useMyTasks, useSetTaskDone } from "../lib/queries";
import { PageHeader } from "./AppShell";
import { TaskRow } from "./TaskRow";

/**
 * My Tasks at `/tasks` (milestone 4.1, `docs/FEATURES.md` §8): every action
 * item assigned to the reader, across every deal they can still see.
 *
 * A screen of its own rather than a panel on the dashboard, because the
 * question it answers is not about one deal — it is the list a rep opens in the
 * morning. The dashboard carries the *count* of what is overdue and links here
 * (`app/DashboardPage.tsx`), which is the split `docs/UX.md` asks for: a number
 * where you already are, the list where you go to work through it.
 *
 * Grouped by standing rather than sorted flat. The server returns tasks soonest
 * first with the undated last, and that order is already correct inside each
 * group — so the grouping is a reading aid over the server's ordering, not a
 * re-sort of it.
 */
const groupOrder: TaskStanding[] = ["overdue", "today", "upcoming", "undated"];

const groupLabels: Record<TaskStanding, string> = {
  overdue: "Overdue",
  today: "Due today",
  upcoming: "Coming up",
  undated: "No date",
  done: "Done",
};

export function TasksPage() {
  const tasks = useMyTasks();
  // One hook for the whole page: the route takes a task id, so nothing here
  // needs one per deal.
  const setDone = useSetTaskDone();
  const today = todayIsoDate();

  const grouped = new Map<TaskStanding, Task[]>();
  for (const task of tasks.data ?? []) {
    const standing = taskStanding(task, today);
    grouped.set(standing, [...(grouped.get(standing) ?? []), task]);
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <PageHeader
          title="My tasks"
          subtitle={
            <p className="page-subtitle">
              Everything assigned to you, across every deal you can see.
            </p>
          }
        />
        {tasks.isError && <p className="error">{tasks.error.message}</p>}
        {tasks.isPending && <p className="status">Loading your tasks...</p>}
        {tasks.data && tasks.data.length === 0 && (
          <section className="onboarding-panel">
            <h2>Nothing is assigned to you.</h2>
            <p>
              Tasks you are given on an opportunity appear here, soonest first.
              Open a deal to write one.
            </p>
          </section>
        )}
        {groupOrder.map((standing) => {
          const group = grouped.get(standing) ?? [];
          if (group.length === 0) {
            return null;
          }
          return (
            <section className="task-group" key={standing}>
              <div className="section-heading">
                <h2>{groupLabels[standing]}</h2>
                <span>{group.length}</span>
              </div>
              <ul className="task-list">
                {group.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    today={today}
                    showOpportunity
                    onToggle={(completed) =>
                      setDone.mutate({ taskId: task.id, completed })
                    }
                  />
                ))}
              </ul>
            </section>
          );
        })}
      </section>
    </main>
  );
}
