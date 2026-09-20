"use client";

import { useState } from "react";

import { confirmDelete } from "../lib/confirm";
import type { Access, TimelineNote } from "../lib/domain";
import {
  useAddComment,
  useDeleteComment,
  useDeleteNote,
  useSaveNote,
} from "../lib/queries";
import { MarkdownText } from "./MarkdownText";

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
  const [draft, setDraft] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const saveNote = useSaveNote();
  const deleteNote = useDeleteNote();
  const addComment = useAddComment();
  const deleteComment = useDeleteComment();

  const failure = [saveNote, deleteNote, addComment, deleteComment].find(
    (mutation) => mutation.isError,
  );

  function save() {
    const body = (draft ?? "").trim();
    if (!body) {
      return;
    }
    saveNote.mutate(
      { noteId: note.id, body },
      { onSuccess: () => setDraft(null) },
    );
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
            <button
              type="button"
              className="secondary-button"
              onClick={() => setDraft(note.body)}
            >
              Edit
            </button>
            <button
              type="button"
              className="danger-button"
              onClick={() => {
                if (confirmDelete("this note and its comments")) {
                  deleteNote.mutate(note.id);
                }
              }}
            >
              Delete
            </button>
          </div>
        )}
      </div>

      {draft !== null ? (
        <div className="stacked-form">
          <textarea
            aria-label="Edit this note"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={3}
          />
          <div className="inline-actions">
            <button type="button" className="primary-button" onClick={save}>
              Save
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setDraft(null)}
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
                onClick={() => {
                  if (confirmDelete("this comment")) {
                    deleteComment.mutate(item.id);
                  }
                }}
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
          />
          <button type="button" className="secondary-button" onClick={post}>
            Post
          </button>
        </div>
      )}
    </section>
  );
}
