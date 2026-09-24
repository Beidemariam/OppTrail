"use client";

import { useRef, useState } from "react";

import { type Access, type TimelineNote } from "../lib/domain";
import { submitOnModEnter } from "../lib/keyboard";
import { normalizeMarkdown } from "../lib/markdown";
import {
  useAddComment,
  useDeleteComment,
  useDeleteNote,
  useRestoreComment,
  useRestoreNote,
  useSaveNote,
} from "../lib/queries";
import { useInlineEditor } from "./InlineEdit";
import { MarkdownText } from "./MarkdownText";
import { Composer, RichTextEditor } from "./RichTextEditor";
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
  // rule every inline editor now shares — the editor takes focus when it
  // opens, and the Edit button takes it back when it closes, so a keyboard
  // reader is never returned to the top of the timeline. Since 3.1 the editor
  // is the rich composer, which takes focus itself on open (`autoFocus`) —
  // ProseMirror has not created the editable element yet when the hook's
  // effect runs.
  const editTriggerRef = useRef<HTMLButtonElement>(null);
  const editor = useInlineEditor(editTriggerRef);
  const [draft, setDraft] = useState("");
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
    // The editor writes the structure back out in its own syntax, so a body
    // reopened and saved untouched can differ from the stored text character
    // for character while saying the same thing. Comparing against the
    // normalized original is what keeps that from writing a version row and
    // an edit marker for an edit nobody made (`lib/markdown.ts`).
    if (body === normalizeMarkdown(note.body)) {
      editor.close();
      return;
    }
    saveNote.mutate({ noteId: note.id, body }, { onSuccess: editor.close });
  }

  return (
    <section className="note-block">
      <div className="note-header">
        <p>
          {note.author_name}
          {note.edited ? " | edited" : ""}
        </p>
        {/* The note's own history is read in the opportunity's history
            dialog, which is the one destination since 3.1c (D-121). */}
        {access.canChangeItem(note.created_by) && (
          <div className="inline-actions">
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
          <RichTextEditor
            label="Edit this note"
            placeholder="Write a note"
            value={draft}
            onChange={setDraft}
            onKeyDown={submitOnModEnter(save)}
            autoFocus
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
        <Composer
          label="Add a comment to this note"
          trigger="Add comment"
          placeholder="Write a comment"
          submitLabel="Post"
          onSubmit={(body) => addComment.mutateAsync({ noteId: note.id, body })}
        />
      )}
    </section>
  );
}
