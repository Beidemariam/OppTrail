"use client";

import { useRef, useState } from "react";

import { usePrivateNote, useSavePrivateNote } from "../lib/queries";
import { formatTimestamp } from "../lib/time";
import { useInlineEditor } from "./InlineEdit";
import { MarkdownText } from "./MarkdownText";
import { RichTextEditor } from "./RichTextEditor";

/**
 * A notebook of one's own, beside the deal (milestone R.1b).
 *
 * The second half of the human's ruling: a sealed entry keeps a *moment* to
 * its author inside the deal's history, and this keeps a *running note* out of
 * that history altogether. One per person per deal, Markdown like every other
 * body in this app, and read by nothing else — not search, not the export, not
 * the AI, not the activity log.
 *
 * Collapsed behind its own trigger like every other writing surface since 3.7,
 * and for the same reason: the rail is for what the reader came to the deal
 * for, and private notes are something you reach for rather than read past.
 * Its heading says who can see it, because that is the whole point of it and
 * a panel that merely says "Notes" would be a panel somebody writes the wrong
 * thing into.
 */
export function PrivateNotePanel({ opportunityId }: { opportunityId: number }) {
  const note = usePrivateNote(opportunityId);
  const save = useSavePrivateNote(opportunityId);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const editorRef = useRef<HTMLDivElement>(null);
  const editor = useInlineEditor(triggerRef, editorRef);
  const [draft, setDraft] = useState("");

  const body = note.data?.body ?? "";

  function open() {
    setDraft(body);
    editor.open();
  }

  function submit() {
    save.mutate(draft, { onSuccess: () => editor.close() });
  }

  return (
    <section className="private-note-panel">
      <div className="section-heading">
        <h3>My notes</h3>
        <span>Only you</span>
      </div>

      {note.isError && <p className="error">{note.error.message}</p>}

      {editor.editing ? (
        <div ref={editorRef}>
          <RichTextEditor
            label="My private notes on this deal"
            placeholder="What you are thinking about this deal"
            value={draft}
            onChange={setDraft}
          />
          <div className="inline-actions">
            <button
              type="button"
              className="primary-button"
              onClick={submit}
              disabled={save.isPending}
            >
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
          {save.isError && <p className="error">{save.error.message}</p>}
        </div>
      ) : body ? (
        <>
          <MarkdownText content={body} />
          <p className="meta-row">
            {note.data?.updated_at
              ? `Saved ${formatTimestamp(note.data.updated_at)}`
              : ""}
          </p>
          <button
            ref={triggerRef}
            type="button"
            className="secondary-button"
            onClick={open}
          >
            Edit my notes
          </button>
        </>
      ) : (
        <button
          ref={triggerRef}
          type="button"
          className="composer-trigger"
          onClick={open}
        >
          Keep a note on this deal, just for you
        </button>
      )}
    </section>
  );
}
