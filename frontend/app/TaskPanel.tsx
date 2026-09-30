"use client";

import { FormEvent, useRef, useState, type RefObject } from "react";

import { todayIsoDate, type Access, type Task } from "../lib/domain";
import {
  useCreateTask,
  useDeleteTask,
  useEditTask,
  useMembers,
  useRestoreTask,
  useSetTaskDone,
  useTasks,
} from "../lib/queries";
import { useInlineEditor } from "./InlineEdit";
import { RichTextEditor } from "./RichTextEditor";
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
  const setDone = useSetTaskDone();
  const deleteTask = useDeleteTask();
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
              <TaskActions
                opportunityId={opportunityId}
                task={task}
                onDelete={() => removeWithUndo(task.id)}
              />
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
 * Edit and Delete on one task (milestone 4.2a).
 *
 * Milestone 4.1 shipped a `PATCH` route with nothing that called it: the panel
 * offered Delete and no way to change a title, a date or — the one the reviewer
 * asked for by name — who a task is assigned to. The editor replaces the row's
 * own body through `useInlineEditor`, the rule this app applies everywhere
 * content is edited where it is read (2.11), so a reader is not moved to a form
 * elsewhere on the page.
 */
function TaskActions({
  opportunityId,
  task,
  onDelete,
}: {
  opportunityId: number;
  task: Task;
  onDelete: () => void;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const editor = useInlineEditor(triggerRef, titleRef);

  if (editor.editing) {
    return (
      <TaskFields
        opportunityId={opportunityId}
        task={task}
        titleRef={titleRef}
        onDone={editor.close}
      />
    );
  }

  return (
    <div className="inline-actions">
      <button
        type="button"
        ref={triggerRef}
        className="secondary-button"
        onClick={editor.open}
      >
        Edit
      </button>
      <button type="button" className="danger-button" onClick={onDelete}>
        Delete
      </button>
    </div>
  );
}

/**
 * A task's fields, for writing a new one or changing an existing one
 * (milestone 4.2a).
 *
 * One component for both, because the fields are the same four and a second
 * copy is how two forms come to disagree about what a task has. `task` is
 * `null` when composing; everything else follows from that — which route is
 * called, what the submit button says, and whether the fields start empty.
 *
 * The description is the rich composer, like every other body in this app
 * (`app/RichTextEditor.tsx`), so `**bold**` and a list work here for the same
 * reason they work in a note.
 */
function TaskFields({
  opportunityId,
  task,
  titleRef,
  onDone,
}: {
  opportunityId: number;
  task: Task | null;
  titleRef?: RefObject<HTMLInputElement | null>;
  onDone: () => void;
}) {
  const create = useCreateTask(opportunityId);
  const edit = useEditTask(opportunityId);
  const members = useMembers(opportunityId);
  const [title, setTitle] = useState(task?.title ?? "");
  const [description, setDescription] = useState(task?.description ?? "");
  const [assignee, setAssignee] = useState(() => {
    // The stored assignee is an id; this control is keyed by email, so the
    // current value is resolved from the member list once it arrives. Seeded
    // empty and corrected below rather than left blank, because a saved edit
    // that silently unassigned somebody would be the worst kind of bug here.
    return "";
  });
  const [assigneeReady, setAssigneeReady] = useState(task === null);
  const [dueDate, setDueDate] = useState(task?.due_date ?? "");

  const people = members.data ?? [];
  if (!assigneeReady && people.length > 0) {
    setAssigneeReady(true);
    const current = people.find(
      (member) => member.user_id === task?.assignee_id,
    );
    setAssignee(current?.email ?? "");
  }

  const save = task ? edit : create;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = {
      title,
      description,
      assignee_email: assignee || null,
      due_date: dueDate || null,
    };
    const done = { onSuccess: () => onDone() };
    if (task) {
      edit.mutate({ taskId: task.id, patch: fields }, done);
    } else {
      create.mutate(fields, done);
    }
  }

  return (
    <form className="task-form" onSubmit={submit}>
      {/* A visible caption *and* an `aria-label` on each control, the pattern
          `OpportunityFilterBar` established (2.13, **D-082**). It matters more
          here than as a convention: a `<label>` wrapping a `<select>` computes
          its accessible name from the label's whole text content, which for the
          assignee was "ForNobody yetAlex Rivera" — every option concatenated.
          That is what a screen reader would have announced, and it is why an
          exact-name query could not find the control at all. */}
      <label>
        Task
        <input
          ref={titleRef}
          aria-label="Task title"
          value={title}
          placeholder="Call them back"
          onChange={(event) => setTitle(event.target.value)}
          required
        />
      </label>
      <div className="field">
        <span className="field-caption">Description</span>
        <RichTextEditor
          label="Task description"
          placeholder="Anything worth saying about it"
          value={description}
          onChange={setDescription}
        />
      </div>
      <label>
        For
        <select
          aria-label="Who this task is for"
          value={assignee}
          onChange={(event) => setAssignee(event.target.value)}
        >
          <option value="">Nobody yet</option>
          {people.map((member) => (
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
          aria-label="When this task is due"
          value={dueDate}
          onChange={(event) => setDueDate(event.target.value)}
        />
      </label>
      <div className="inline-actions">
        <button className="primary-button" type="submit">
          {task ? "Save Task" : "Add Task"}
        </button>
        <button className="secondary-button" type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
      {save.isError && <p className="error">{save.error.message}</p>}
    </form>
  );
}

/**
 * Writing a task down, behind the trigger that reveals the fields.
 *
 * The fields themselves are `TaskFields` above, shared with the editor: a
 * composer and an editor over the same four values were two copies of one form
 * until milestone 4.2a, and two copies is how they come to disagree.
 */
function TaskComposer({ opportunityId }: { opportunityId: number }) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const composer = useInlineEditor(triggerRef, titleRef);

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
    <TaskFields
      opportunityId={opportunityId}
      task={null}
      titleRef={titleRef}
      onDone={composer.close}
    />
  );
}
