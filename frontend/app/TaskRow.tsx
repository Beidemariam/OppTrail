"use client";

import { Link } from "react-router";

import { taskStanding, type Task } from "../lib/domain";
import { MarkdownText } from "./MarkdownText";

/**
 * One task, as a row (milestone 4.1).
 *
 * Shared by My Tasks and by an opportunity's own list, because a task reads the
 * same way in both and the only difference is whether the deal's name is worth
 * printing — on the deal's own screen it is the screen's title.
 *
 * The checkbox is the whole control. A task has exactly one thing a reader does
 * to it in passing, which is tick it off; editing and deleting live in the
 * opportunity's list where the task was written, not on a cross-deal summary
 * (`docs/UX.md`'s Design bar: an affordance on every value in every view is the
 * clutter to avoid).
 */
export function TaskRow({
  task,
  today,
  showOpportunity = false,
  onToggle,
  children,
}: {
  task: Task;
  today: string;
  showOpportunity?: boolean;
  onToggle: (completed: boolean) => void;
  /** Controls the opportunity's own list adds: edit, delete. */
  children?: React.ReactNode;
}) {
  const standing = taskStanding(task, today);
  const done = Boolean(task.completed_at);

  return (
    <li className="task-row" data-standing={standing}>
      <label className="task-check">
        <input
          type="checkbox"
          checked={done}
          onChange={(event) => onToggle(event.target.checked)}
        />
        {/* The title is the checkbox's own label, so the box is named by what
            it completes rather than by the word "done" repeated down the page. */}
        <span className="task-title">{task.title}</span>
      </label>

      {/* Markdown, like every other body in this app (milestone 4.2a): the
          composer writes it and one renderer reads it, so a list typed into a
          task's description shows as a list rather than as dashes. */}
      {task.description && (
        <div className="task-description">
          <MarkdownText content={task.description} />
        </div>
      )}

      <p className="meta-row task-meta">
        {showOpportunity && (
          <Link to={`/opportunities/${task.opportunity_id}`}>
            {task.opportunity_name}
          </Link>
        )}
        {task.due_date ? (
          <span className="task-due">
            {standing === "overdue" ? "Overdue " : "Due "}
            {task.due_date}
          </span>
        ) : (
          <span className="task-due">No date</span>
        )}
        {/* Every name, since a task can be for more than one person
            (milestone 4.6). Joined rather than listed: this is a meta row, and
            two people are the normal case rather than a list worth its own
            layout. */}
        {task.assignees.length > 0 && (
          <span>{task.assignees.map((item) => item.name).join(", ")}</span>
        )}
        {/* An entry's title rather than its id: the link is the reader's way
            back to why the task exists (D-124's shape). `entry_title` is null
            once that entry is deleted, and the task stays. */}
        {task.entry_id && task.entry_title && (
          <Link
            to={`/opportunities/${task.opportunity_id}?entry=${task.entry_id}`}
          >
            {task.entry_title}
          </Link>
        )}
        {done && task.completed_by_name && (
          <span>Done by {task.completed_by_name}</span>
        )}
      </p>

      {children}
    </li>
  );
}
