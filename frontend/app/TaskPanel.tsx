"use client";

import { FormEvent, useRef, useState } from "react";

import {
  taskStanding,
  todayIsoDate,
  type Access,
  type Task,
} from "../lib/domain";
import {
  useCreateTask,
  useDeleteTask,
  useMembers,
  useRestoreTask,
  useSetTaskDone,
  useTasks,
} from "../lib/queries";
import { useInlineEditor } from "./InlineEdit";
import { TaskRow } from "./TaskRow";
import { useUndoableDelete } from "./Toasts";

/**
 * One deal's action items (milestone 4.1, `docs/FEATURES.md` §8).
 *
 * Sits in the sidebar with the deal's own record, because that is where the
 * facts about this opportunity live rather than in its history. Written and
 * completed here; read across deals at `/tasks`.
 *
 * Three shapes reused rather than reinvented:
 *
 * - **The composer is collapsed** behind "Add task", through `useInlineEditor`
 *   like the timeline's entry form (3.7) and a note's `Composer` (D-110), so
 *   the panel is a list until somebody wants to add to it.
 * - **Deleting offers Undo** rather than confirming (`useUndoableDelete`,
 *   2.4b) — a task is soft-deleted and restorable, so the toast is the way
 *   back.
 * - **Done tasks collapse.** They stay readable, because "we already did that"
 *   is what a shared record is for, but they do not sit between the reader and
 *   what is still open.
 */
export function TaskPanel({
  opportunityId,
  access,
}: {
  opportunityId: number;
  access: Access;
}) {
  const tasks = useTasks(opportunityId, true);
  const setDone = useSetTaskDone(opportunityId);
  const deleteTask = useDeleteTask(opportunityId);
  const restoreTask = useRestoreTask();
  const removeWithUndo = useUndoableDelete("Task", deleteTask, restoreTask);
  const [showDone, setShowDone] = useState(false);
  const today = todayIsoDate();

  const all = tasks.data ?? [];
  const open = all.filter((task) => !task.completed_at);
  const done = all.filter((task) => task.completed_at);

  return (
    <section className="task-panel">
      <div className="section-heading">
        <h3>Tasks</h3>
        <span>{open.length} open</span>
      </div>

      {tasks.isError && <p className="error">{tasks.error.message}</p>}

      {open.length === 0 && !tasks.isPending && (
        <p className="empty-state">Nothing outstanding on this deal.</p>
      )}

      <ul className="task-list">
        {open.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            today={today}
            onToggle={(completed) =>
              setDone.mutate({ taskId: task.id, completed })
            }
          >
            {access.canChangeItem(task.created_by) && (
              <div className="inline-actions">
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => removeWithUndo(task.id)}
                >
                  Delete
                </button>
              </div>
            )}
          </TaskRow>
        ))}
      </ul>

      {done.length > 0 && (
        <>
          <button
            type="button"
            className="disclosure-button"
            aria-expanded={showDone}
            onClick={() => setShowDone(!showDone)}
          >
            <span aria-hidden="true">{showDone ? "-" : "+"}</span> Done (
            {done.length})
          </button>
          {showDone && (
            <ul className="task-list">
              {done.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  today={today}
                  onToggle={(completed) =>
                    setDone.mutate({ taskId: task.id, completed })
                  }
                />
              ))}
            </ul>
          )}
        </>
      )}

      {access.canWriteTimeline && (
        <TaskComposer opportunityId={opportunityId} />
      )}
    </section>
  );
}

/**
 * Writing a task down: a title, optionally who it is for and when it is due.
 *
 * The assignee is a `select` over `useMembers` — the people a task can actually
 * reach on this deal, which is the same list the composer's `@` trigger offers
 * (3.2, D-123) — rather than a typed email. A task is for a colleague on the
 * deal, and asking somebody to remember an address is the mistake requirement
 * 13 already made once.
 */
function TaskComposer({ opportunityId }: { opportunityId: number }) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const composer = useInlineEditor(triggerRef, titleRef);
  const create = useCreateTask(opportunityId);
  const members = useMembers(opportunityId);
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState("");
  const [dueDate, setDueDate] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate(
      {
        title,
        assignee_email: assignee || null,
        due_date: dueDate || null,
      },
      {
        onSuccess: () => {
          setTitle("");
          setAssignee("");
          setDueDate("");
          composer.close();
        },
      },
    );
  }

  if (!composer.editing) {
    return (
      <p className="compose-trigger">
        <button
          type="button"
          ref={triggerRef}
          className="secondary-button"
          aria-expanded={false}
          onClick={composer.open}
        >
          Add task
        </button>
      </p>
    );
  }

  return (
    <form className="task-form" onSubmit={submit}>
      <label>
        Task
        <input
          ref={titleRef}
          value={title}
          placeholder="Call them back"
          onChange={(event) => setTitle(event.target.value)}
          required
        />
      </label>
      <label>
        For
        <select
          value={assignee}
          onChange={(event) => setAssignee(event.target.value)}
        >
          <option value="">Nobody yet</option>
          {(members.data ?? []).map((member) => (
            <option key={member.email} value={member.email}>
              {member.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Due
        <input
          type="date"
          value={dueDate}
          onChange={(event) => setDueDate(event.target.value)}
        />
      </label>
      <div className="inline-actions">
        <button className="primary-button" type="submit">
          Add Task
        </button>
        <button
          className="secondary-button"
          type="button"
          onClick={composer.close}
        >
          Cancel
        </button>
      </div>
      {create.isError && <p className="error">{create.error.message}</p>}
    </form>
  );
}
