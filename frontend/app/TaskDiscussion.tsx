"use client";

import { type Access, type Task } from "../lib/domain";
import {
  useAddTaskComment,
  useDeleteTaskComment,
  useRestoreTaskComment,
} from "../lib/queries";
import { formatTimestamp } from "../lib/time";
import { MarkdownText } from "./MarkdownText";
import { Composer } from "./RichTextEditor";
import { useUndoableDelete } from "./Toasts";

/**
 * The discussion on one task (milestone 4.5, **D-162**).
 *
 * **Flat and chronological**, which is the whole shape: no reply, no resolve,
 * no reaction. A note's comments are a place two people argue about what a
 * record means; a task's are a log of what happened to it — "chased them, no
 * answer", "moved to Thursday" — and `docs/FEATURES.md` §8's warning about
 * becoming a task manager is the reason not to rebuild milestone 3.3 here.
 *
 * Everything else is the shape already in use: the composer is collapsed
 * behind a trigger (D-110), a comment is Markdown rendered by `MarkdownText`
 * like every other body, deleting offers Undo rather than confirming (2.4b),
 * and a comment cannot be edited at all (`AGENTS.md` invariant 2) — so Delete
 * is the only control on one.
 */
export function TaskDiscussion({
  task,
  access,
}: {
  task: Task;
  access: Access;
}) {
  const add = useAddTaskComment();
  const removeWithUndo = useUndoableDelete(
    "Comment",
    useDeleteTaskComment(),
    useRestoreTaskComment(),
  );

  if (task.comments.length === 0 && !access.canWriteTimeline) {
    return null;
  }

  return (
    <div className="task-discussion">
      {task.comments.length > 0 && (
        <ul>
          {task.comments.map((comment) => (
            <li key={comment.id} className="task-comment">
              <p className="meta-row">
                {comment.author_name} | {formatTimestamp(comment.created_at)}
              </p>
              <MarkdownText content={comment.body} />
              {access.canChangeItem(comment.created_by) && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => removeWithUndo(comment.id)}
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {access.canWriteTimeline && (
        <Composer
          label="Comment on this task"
          trigger="Comment"
          placeholder="What happened with this?"
          submitLabel="Add Comment"
          onSubmit={(body) => add.mutateAsync({ taskId: task.id, body })}
        />
      )}
      {add.isError && <p className="error">{add.error.message}</p>}
    </div>
  );
}
