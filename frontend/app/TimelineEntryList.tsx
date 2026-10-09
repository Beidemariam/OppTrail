"use client";

import { useEffect, useRef } from "react";

import { type Access, type TimelineEntry } from "../lib/domain";
import {
  useAddNote,
  useDeleteTimelineEntry,
  useRestoreTimelineEntry,
} from "../lib/queries";
import { formatTimestamp } from "../lib/time";
import { AttachmentList } from "./AttachmentList";
import { EntryTypeBadge } from "./EntryTypeBadge";
import { useInlineEditor } from "./InlineEdit";
import { MarkdownText } from "./MarkdownText";
import { NoteBlock } from "./NoteBlock";
import { Composer } from "./RichTextEditor";
import { TimelineEntryForm } from "./TimelineEntryForm";
import { useUndoableDelete } from "./Toasts";

/** The opportunity's history, in the order the API returned it. */
export function TimelineEntryList({
  entries,
  opportunityId,
  access,
  linkedEntryId,
}: {
  entries: TimelineEntry[];
  opportunityId: number;
  access: Access;
  /** The entry a link pointed at, if the reader arrived through one
   * (milestone 3.2, `?entry=` in `app/OpportunityPanel.tsx`). */
  linkedEntryId?: number | null;
}) {
  if (entries.length === 0) {
    return <p className="empty-state">No timeline entries match this view.</p>;
  }

  return (
    <div className="timeline-list">
      {entries.map((entry) => (
        <TimelineEntryCard
          key={entry.id}
          entry={entry}
          opportunityId={opportunityId}
          access={access}
          linked={entry.id === linkedEntryId}
        />
      ))}
    </div>
  );
}

/**
 * One entry, and — since milestone 2.11 — its editor.
 *
 * Edit swaps this card's own body for the entry form, in the space the entry
 * occupied, with the entries above and below it still on screen. It used to
 * load the entry into the composer at the top of the panel, which moved a
 * reader fifty entries down back to the top of the page and lost their place
 * (D-051); nothing about the write changed, only where the reader does it.
 */
function TimelineEntryCard({
  entry,
  opportunityId,
  access,
  linked,
}: {
  entry: TimelineEntry;
  opportunityId: number;
  access: Access;
  /** Whether a link brought the reader here (milestone 3.2). */
  linked: boolean;
}) {
  // A link to an entry lands on the entry, not on the top of its timeline
  // (milestone 3.2, D-124): the card scrolls itself into view and stays marked
  // for as long as the URL names it, which is what tells the reader which of
  // fifty cards the note they came from was talking about.
  const cardRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (linked) {
      cardRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [linked]);
  const editTriggerRef = useRef<HTMLButtonElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const editor = useInlineEditor(editTriggerRef, titleRef);
  const addNote = useAddNote();
  const deleteEntry = useDeleteTimelineEntry();
  const remove = useUndoableDelete(
    "Timeline entry",
    deleteEntry,
    useRestoreTimelineEntry(),
  );

  const failure = [addNote, deleteEntry].find((mutation) => mutation.isError);

  return (
    <article
      className={`timeline-entry${linked ? " is-linked" : ""}`}
      ref={cardRef}
    >
      <div className={`timeline-marker ${entry.type}`} />
      <div className="timeline-entry-body">
        <div className="timeline-entry-header">
          <div>
            <div className="meta-row">
              {/* The entry's number within this deal (3.8, changed to a
                  per-deal sequence in 3.9 by **D-139**). The AI cites entries
                  by this number, so the card has to print the same one: the
                  server computes it once
                  (`timeline_utils.ENTRY_SEQUENCE_SQL`) and both read it,
                  rather than each side counting. #1 is the oldest thing that
                  happened here, which is what a person counting a timeline
                  counts -- the row id, which this used to show, is still what
                  `?entry=` links carry. */}
              <span className="entry-number">#{entry.sequence}</span>
              <EntryTypeBadge type={entry.type} />
              {entry.system_generated && (
                <span className="system-badge">System</span>
              )}
              <span>{formatTimestamp(entry.event_timestamp)}</span>
            </div>
            <h3>{entry.title}</h3>
            {/* An entry body is Markdown, the same as a note's and a
                comment's: one composer writes all three (milestone 3.1), so
                one renderer reads them. It used to print as plain text, which
                is why a body written with a list showed its dashes
                (**D-108**). */}
            {entry.body ? (
              <MarkdownText content={entry.body} />
            ) : (
              <p className="timeline-copy">No details</p>
            )}
          </div>
          {/* A system entry is history, not content: it cannot be edited or
              deleted through the API (`AGENTS.md`, auditability). What an
              edit to an ordinary entry replaced is read in the opportunity's
              own history rather than from a button here (3.1c, D-121). */}
          {access.canChangeItem(entry.created_by) &&
            !entry.system_generated && (
              <div className="inline-actions">
                <button
                  ref={editTriggerRef}
                  type="button"
                  className="secondary-button"
                  onClick={editor.open}
                >
                  Edit
                </button>
                {/* No confirmation: the entry goes, and the toast offers the
                    way back (`docs/UX.md`, milestone 2.4b). */}
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => remove(entry.id)}
                >
                  Delete
                </button>
              </div>
            )}
        </div>
        <p className="meta-row">
          By {entry.author_name ?? "System"}
          {entry.follow_up_date ? ` | Follow up ${entry.follow_up_date}` : ""}
        </p>

        {editor.editing && (
          <TimelineEntryForm
            opportunityId={opportunityId}
            editing={entry}
            titleRef={titleRef}
            onDone={editor.close}
          />
        )}

        {failure && <p className="error">{failure.error?.message}</p>}

        {/* The entry's documents, between what happened and what was said
            about it (milestone 4.3): a proposal belongs to the entry that
            records sending it, and the notes under it are the discussion. */}
        <AttachmentList entry={entry} access={access} />

        <div className="notes-list">
          {entry.notes.map((item) => (
            <NoteBlock key={item.id} note={item} access={access} />
          ))}

          {access.canWriteTimeline && (
            <Composer
              label="Add a note to this entry"
              trigger="Add note"
              placeholder="Write a note"
              submitLabel="Add Note"
              onSubmit={(body) =>
                addNote.mutateAsync({ entryId: entry.id, body })
              }
            />
          )}
        </div>
      </div>
    </article>
  );
}
