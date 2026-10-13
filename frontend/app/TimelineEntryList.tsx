"use client";

import { useRef } from "react";

import {
  type Access,
  type CustomValues,
  type LinkTarget,
  type TimelineEntry,
  cardCustomValues,
  isLinked,
} from "../lib/domain";
import {
  useAddNote,
  useCustomFields,
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
import { useLinkTarget } from "./useLinkTarget";

/** The opportunity's history, in the order the API returned it. */
export function TimelineEntryList({
  entries,
  opportunityId,
  access,
  linkTarget,
}: {
  entries: TimelineEntry[];
  opportunityId: number;
  access: Access;
  /** What a link pointed at, if the reader arrived through one (milestone
   * 3.2 for an entry, 6.0 for the two levels below it). Passed whole rather
   * than one id per level, so a new level is a case in `isLinked` instead of
   * another prop threaded through three components. */
  linkTarget?: LinkTarget | null;
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
          linkTarget={linkTarget}
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
  linkTarget,
}: {
  entry: TimelineEntry;
  opportunityId: number;
  access: Access;
  /** What a link brought the reader to, at any level (milestone 3.2, 6.0). */
  linkTarget?: LinkTarget | null;
}) {
  // A link to an entry lands on the entry, not on the top of its timeline
  // (milestone 3.2, D-124): the card scrolls itself into view and stays marked
  // for as long as the URL names it, which is what tells the reader which of
  // fifty cards the note they came from was talking about. The scroll moved
  // into `useLinkTarget` in milestone 6.0, when notes and comments needed the
  // same behaviour.
  const linked = isLinked(linkTarget, "entry", entry.id);
  const cardRef = useLinkTarget<HTMLElement>(linked);
  const entryFields = useCustomFields("entry");
  const customValues = cardCustomValues(
    entryFields.data ?? [],
    (entry.custom_values ?? {}) as CustomValues,
  );
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
                <span className="system-badge">
                  {entry.automation_rule_id === null ? "System" : "Automation"}
                </span>
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
          {/* A system entry is history, not content: it cannot be edited
              through the API at all (`AGENTS.md`, auditability). What an
              edit to an ordinary entry replaced is read in the opportunity's
              own history rather than from a button here (3.1c, D-121).

              **Deleting one is the exception an automation earns** (6.3a,
              **D-181**, the human's request at the 6.3 review): a mistaken
              rule leaves entries on a deal and somebody has to be able to
              clear them up. So an automation's entry offers Delete and not
              Edit — removing a mistake is not rewriting what the record says
              — while a system entry a *person* caused offers neither. The
              permission is unchanged: `canChangeItem` is author-or-owner, and
              an automated entry's author is the rule's creator. */}
          {access.canChangeItem(entry.created_by) &&
            (!entry.system_generated || entry.automation_rule_id !== null) && (
              <div className="inline-actions">
                {!entry.system_generated && (
                  <button
                    ref={editTriggerRef}
                    type="button"
                    className="secondary-button"
                    onClick={editor.open}
                  >
                    Edit
                  </button>
                )}
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
        {/* What this team decided to track on an entry (6.2a, the human's
            request at the 6.2 review). `cardCustomValues` is where the two
            rules live: an unset value is not shown, and a `false` yes/no is
            not shown either -- "Follow up: No" is an absence taking up the
            room of a fact. */}
        {customValues.length > 0 && (
          <p className="meta-row entry-custom-values">
            {customValues.map(({ field, text }) => (
              <span key={field.key} className="custom-value-chip">
                {field.type === "checkbox"
                  ? field.label
                  : `${field.label}: ${text}`}
              </span>
            ))}
          </p>
        )}

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
            <NoteBlock
              key={item.id}
              note={item}
              access={access}
              linkTarget={linkTarget}
            />
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
