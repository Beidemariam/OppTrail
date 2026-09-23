"use client";

import { useRef } from "react";

import {
  timelineEntryVersionFields,
  type Access,
  type TimelineEntry,
} from "../lib/domain";
import {
  useAddNote,
  useDeleteTimelineEntry,
  useRestoreTimelineEntry,
  useTimelineEntryVersions,
} from "../lib/queries";
import { formatTimestamp } from "../lib/time";
import { EntryTypeBadge } from "./EntryTypeBadge";
import { HistoryButton } from "./HistoryDialog";
import { useInlineEditor } from "./InlineEdit";
import { MarkdownText } from "./MarkdownText";
import { NoteBlock } from "./NoteBlock";
import { Composer } from "./RichTextEditor";
import { TimelineEntryForm } from "./TimelineEntryForm";
import { useUndoableDelete } from "./Toasts";

/** The opportunity's history, oldest first, as the API ordered it. */
export function TimelineEntryList({
  entries,
  opportunityId,
  access,
}: {
  entries: TimelineEntry[];
  opportunityId: number;
  access: Access;
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
}: {
  entry: TimelineEntry;
  opportunityId: number;
  access: Access;
}) {
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
    <article className="timeline-entry">
      <div className={`timeline-marker ${entry.type}`} />
      <div className="timeline-entry-body">
        <div className="timeline-entry-header">
          <div>
            <div className="meta-row">
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
              deleted through the API (`AGENTS.md`, auditability), so it has no
              edit history either. */}
          {access.canChangeItem(entry.created_by) &&
            !entry.system_generated && (
              <div className="inline-actions">
                {/* Editing is the author's or the owner's; reading what an
                    edit replaced is the owner's alone (milestone 2.10). */}
                {access.canManage && (
                  <HistoryButton
                    title="History of this timeline entry"
                    fields={timelineEntryVersionFields}
                    itemId={entry.id}
                    useVersions={useTimelineEntryVersions}
                  />
                )}
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
