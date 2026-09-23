"use client";

import { useRef, useState } from "react";

import {
  noteVersionFields,
  type Access,
  type TimelineNote,
} from "../lib/domain";
import { submitOnModEnter } from "../lib/keyboard";
import {
  useAddComment,
  useDeleteComment,
  useDeleteNote,
  useNoteVersions,
  useRestoreComment,
  useRestoreNote,
  useSaveNote,
} from "../lib/queries";
import { HistoryButton } from "./HistoryDialog";
import { useInlineEditor } from "./InlineEdit";
import { MarkdownText } from "./MarkdownText";
import { useUndoableDelete } from "./Toasts";

/**
 * One note, its comments, and the controls the reader is allowed to see.
 *
 * Comments are immutable (`AGENTS.md` invariant 2) — there is no edit control
 * here because there is no route behind one.
 */
export function NoteBlock({
  note,
  access,
}: {
  note: TimelineNote;
  access: Access;
}) {
  // Editing a note has always happened in the note (`docs/UX.md`), so
  // milestone 2.11 changed nothing about where; what it added is the focus
  // rule every inline editor now shares — the textarea takes focus when it
  // opens, and the Edit button takes it back when it closes, so a keyboard
  // reader is never returned to the top of the timeline.
  const editTriggerRef = useRef<HTMLButtonElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const editor = useInlineEditor(editTriggerRef, bodyRef);
  const [draft, setDraft] = useState("");
  const [comment, setComment] = useState("");
  const saveNote = useSaveNote();
  const deleteNote = useDeleteNote();
  const addComment = useAddComment();
  const deleteComment = useDeleteComment();
  const removeNote = useUndoableDelete("Note", deleteNote, useRestoreNote());
  const removeComment = useUndoableDelete(
    "Comment",
    deleteComment,
    useRestoreComment(),
  );

  const failure = [saveNote, deleteNote, addComment, deleteComment].find(
    (mutation) => mutation.isError,
  );

  function save() {
    const body = draft.trim();
    if (!body) {
      return;
    }
    saveNote.mutate({ noteId: note.id, body }, { onSuccess: editor.close });
  }

  function post() {
    const body = comment.trim();
    if (!body) {
      return;
    }
    addComment.mutate(
      { noteId: note.id, body },
      { onSuccess: () => setComment("") },
    );
  }

  return (
    <section className="note-block">
      <div className="note-header">
        <p>
          {note.author_name}
          {note.edited ? " | edited" : ""}
        </p>
        {access.canChangeItem(note.created_by) && (
          <div className="inline-actions">
            {/* Owner-only, like the other two histories (milestone 2.10). */}
            {access.canManage && (
              <HistoryButton
                title="History of this note"
                fields={noteVersionFields}
                itemId={note.id}
                useVersions={useNoteVersions}
              />
            )}
            <button
              ref={editTriggerRef}
              type="button"
              className="secondary-button"
              onClick={() => {
                setDraft(note.body);
                editor.open();
              }}
            >
              Edit
            </button>
            <button
              type="button"
              className="danger-button"
              onClick={() => removeNote(note.id)}
            >
              Delete
            </button>
          </div>
        )}
      </div>

      {editor.editing ? (
        <div className="stacked-form">
          <textarea
            ref={bodyRef}
            aria-label="Edit this note"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={submitOnModEnter(save)}
            rows={3}
          />
          <div className="inline-actions">
            <button type="button" className="primary-button" onClick={save}>
              Save
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={editor.close}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <MarkdownText content={note.body} />
      )}

      {failure && <p className="error">{failure.error?.message}</p>}

      <div className="comment-list">
        {note.comments.map((item) => (
          <div className="comment-row" key={item.id}>
            <div>
              <strong>{item.author_name}</strong>
              <MarkdownText content={item.body} />
            </div>
            {access.canChangeItem(item.created_by) && (
              <button
                type="button"
                className="danger-button compact"
                onClick={() => removeComment(item.id)}
              >
                Delete
              </button>
            )}
          </div>
        ))}
      </div>

      {access.canWriteTimeline && (
        <div className="inline-compose">
          <input
            aria-label="Add a comment to this note"
            placeholder="Add comment"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            onKeyDown={submitOnModEnter(post)}
          />
          <button type="button" className="secondary-button" onClick={post}>
            Post
          </button>
        </div>
      )}
    </section>
  );
}
