"use client";

import { useRef, useState } from "react";

import { isConflict } from "../lib/api";
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
import { CommentThread } from "./CommentThread";
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
  // The note as it stood when this editor was opened, which is exactly what
  // ADR 0003's guard compares against. Captured rather than read from `note`
  // on save, because the timeline refetches underneath an open editor as soon
  // as the live stream says somebody else wrote (milestone 3.4): reading the
  // prop would hand the server back the value the *other* person's write
  // produced, and the guard would pass on the one write it exists to stop.
  const [baseline, setBaseline] = useState(note.updated_at);
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
  // The one failure that is about the note rather than about the request
  // (milestone 3.4, ADR 0003): somebody else saved while this editor was open.
  // The reader keeps their draft and the note underneath has already been
  // refetched — the mutation invalidates the timeline whether it succeeded or
  // not — so Cancel is the "reload" the ADR's conflict model offers, and it is
  // named as such rather than left to a generic error line.
  const conflicted = saveNote.isError && isConflict(saveNote.error);

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
    saveNote.mutate(
      { noteId: note.id, body, updatedAt: baseline },
      { onSuccess: editor.close },
    );
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
                setBaseline(note.updated_at);
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
              {conflicted ? "Discard my edit" : "Cancel"}
            </button>
          </div>
        </div>
      ) : (
        <MarkdownText content={note.body} />
      )}

      {conflicted ? (
        <p className="error">
          Somebody else saved this note while you were editing it. Their version
          is what the note says now; copy anything you want to keep, then
          discard your edit.
        </p>
      ) : (
        failure && <p className="error">{failure.error?.message}</p>
      )}

      {/* Since 3.3 a note's comments are threads, not a flat list: each one
          draws its own replies, its Reply control and its resolved state
          (`app/CommentThread.tsx`). Undo stays here, so one toast serves
          every comment on the note. */}
      <div className="comment-list">
        {note.comments.map((thread) => (
          <CommentThread
            key={thread.id}
            thread={thread}
            access={access}
            onDelete={removeComment}
          />
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
