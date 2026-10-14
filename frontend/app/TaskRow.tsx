"use client";

import { Link } from "react-router";

import {
  isLinked,
  taskStanding,
  type LinkTarget,
  type Task,
} from "../lib/domain";
import { MarkdownText } from "./MarkdownText";
import { useLinkTarget } from "./useLinkTarget";

/**
 * One task, as a row (milestone 4.1).
 *
 * Shared by My Tasks and by an opportunity's own list, because a task reads the
 * same way in both and the only difference is whether the deal's name is worth
 * printing — on the deal's own screen it is the screen's title.
 *
 * **The title is not the checkbox's label** (R.1). It was, which meant clicking
 * a task's title on My Tasks ticked it off rather than opening it — the
 * opposite of what a title does everywhere else in this app, and reported as
 * exactly that. The box now carries its own name, and on a cross-deal list the
 * title is a link to the task where it lives: the deal's own panel, which is
 * where it can be read with its description, its assignees and its discussion.
 *
 * On the deal's own panel the title stays plain text, because the task is
 * already open there — a link to the screen you are on is noise.
 */
export function TaskRow({
  task,
  today,
  showOpportunity = false,
  onToggle,
  linkTarget,
  children,
}: {
  task: Task;
  today: string;
  showOpportunity?: boolean;
  onToggle: (completed: boolean) => void;
  /** What a link pointed at, if it pointed at a task (R.1). */
  linkTarget?: LinkTarget | null;
  /** Controls the opportunity's own list adds: edit, delete. */
  children?: React.ReactNode;
}) {
  const standing = taskStanding(task, today);
  const done = Boolean(task.completed_at);
  // The other half of My Tasks' link: the row scrolls itself into view and
  // says which one was named, the way a linked entry, note or comment does
  // (6.0, D-170).
  const linked = isLinked(linkTarget, "task", task.id);
  const ref = useLinkTarget<HTMLLIElement>(linked);

  return (
    <li
      className={linked ? "task-row is-linked" : "task-row"}
      data-standing={standing}
      ref={ref}
    >
      <div className="task-check">
        <input
          type="checkbox"
          checked={done}
          aria-label={`${done ? "Reopen" : "Complete"} ${task.title}`}
          onChange={(event) => onToggle(event.target.checked)}
        />
        {showOpportunity ? (
          <Link
            className="task-title"
            to={`/opportunities/${task.opportunity_id}?task=${task.id}`}
          >
            {task.title}
          </Link>
        ) : (
          <span className="task-title">{task.title}</span>
        )}
      </div>

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
