"use client";

import { useState } from "react";

import type { Access, TimelineEntry } from "../lib/domain";
import { submitOnModEnter } from "../lib/keyboard";
import {
  useAddNote,
  useDeleteTimelineEntry,
  useRestoreTimelineEntry,
} from "../lib/queries";
import { formatTimestamp } from "../lib/time";
import { EntryTypeBadge } from "./EntryTypeBadge";
import { NoteBlock } from "./NoteBlock";
import { useUndoableDelete } from "./Toasts";

/** The opportunity's history, oldest first, as the API ordered it. */
export function TimelineEntryList({
  entries,
  access,
  onEdit,
}: {
  entries: TimelineEntry[];
  access: Access;
  onEdit: (entry: TimelineEntry) => void;
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
          access={access}
          onEdit={onEdit}
        />
      ))}
    </div>
  );
}

function TimelineEntryCard({
  entry,
  access,
  onEdit,
}: {
  entry: TimelineEntry;
  access: Access;
  onEdit: (entry: TimelineEntry) => void;
}) {
  const [note, setNote] = useState("");
  const addNote = useAddNote();
  const deleteEntry = useDeleteTimelineEntry();
  const remove = useUndoableDelete(
    "Timeline entry",
    deleteEntry,
    useRestoreTimelineEntry(),
  );

  const failure = [addNote, deleteEntry].find((mutation) => mutation.isError);

  function add() {
    const body = note.trim();
    if (!body) {
      return;
    }
    addNote.mutate(
      { entryId: entry.id, body },
      { onSuccess: () => setNote("") },
    );
  }

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
            <p className="timeline-copy">{entry.body || "No details"}</p>
          </div>
          {/* A system entry is history, not content: it cannot be edited or
              deleted through the API (`AGENTS.md`, auditability). */}
          {access.canChangeItem(entry.created_by) &&
            !entry.system_generated && (
              <div className="inline-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onEdit(entry)}
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

        {failure && <p className="error">{failure.error?.message}</p>}

        <div className="notes-list">
          {entry.notes.map((item) => (
            <NoteBlock key={item.id} note={item} access={access} />
          ))}

          {access.canWriteTimeline && (
            <div className="inline-compose">
              <input
                aria-label="Add a note to this entry"
                placeholder="Add note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                onKeyDown={submitOnModEnter(add)}
              />
              <button type="button" className="secondary-button" onClick={add}>
                Add Note
              </button>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
