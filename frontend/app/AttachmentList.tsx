"use client";

import { ChangeEvent, useRef } from "react";

import {
  formatBytes,
  type Access,
  type Attachment,
  type TimelineEntry,
} from "../lib/domain";
import {
  attachmentDownloadPath,
  useDeleteAttachment,
  useRestoreAttachment,
  useUploadAttachment,
} from "../lib/queries";
import { useInlineEditor } from "./InlineEdit";
import { useUndoableDelete } from "./Toasts";

/**
 * The files on one timeline entry (milestone 4.3, `docs/FEATURES.md` §6).
 *
 * Drawn on the entry rather than on the deal, because that is what an
 * attachment is: `docs/ROADMAP.md` is explicit that "proposals and contracts
 * attach to the entry they belong to", so the proposal sits on the entry that
 * records sending it. A task is the opposite and lives in the sidebar with the
 * record — an action item is a fact about the deal, not an event on it.
 *
 * Three shapes reused rather than reinvented:
 *
 * - **The picker is collapsed** behind "Attach file", through
 *   `useInlineEditor` like the note composer (D-110) and the entry form (3.7).
 *   A file input permanently open on fifty entry cards is the clutter
 *   `AGENTS.md`'s Design bar rules out.
 * - **Deleting offers Undo** rather than confirming (`useUndoableDelete`,
 *   2.4b): an attachment is soft-deleted and restorable, so the toast is the
 *   way back.
 * - **A download is a link**, like the three export links, not a fetch. The
 *   response is a download (`Content-Disposition: attachment`), which is the
 *   browser's job rather than the data layer's.
 */
export function AttachmentList({
  entry,
  access,
}: {
  entry: TimelineEntry;
  access: Access;
}) {
  // A system entry is history rather than content: it cannot be edited or
  // deleted through the API, and a contract hanging off "Opportunity created"
  // is not what §6 means by attaching a document to what happened. Any file it
  // somehow carries is still listed and still downloadable -- what is withheld
  // is the trigger, the same way Edit and Delete are (milestone 4.3a).
  const canAttach = access.canWriteTimeline && !entry.system_generated;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const picker = useInlineEditor(triggerRef, inputRef);
  const upload = useUploadAttachment();
  const removeWithUndo = useUndoableDelete(
    "Attachment",
    useDeleteAttachment(),
    useRestoreAttachment(),
  );

  async function send(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    // Reset before the request, not after: the input is unmounted by
    // `picker.close()` below, and a retry of the same file has to count as a
    // change event or picking it again would do nothing.
    event.target.value = "";
    // The same shape `Composer.submit` uses: the picker closes when the upload
    // resolves and stays open when it does not, because a refused file leaves
    // the reader with something to do about it -- and the rejection is read
    // from the mutation's own state below rather than thrown on.
    const sent = await upload.mutateAsync({ entryId: entry.id, file }).then(
      () => true,
      () => false,
    );
    if (sent) {
      picker.close();
    }
  }

  if (entry.attachments.length === 0 && !canAttach) {
    return null;
  }

  return (
    <div className="attachment-list">
      {entry.attachments.length > 0 && (
        <ul>
          {entry.attachments.map((attachment) => (
            <AttachmentRow
              key={attachment.id}
              attachment={attachment}
              access={access}
              onDelete={() => removeWithUndo(attachment.id)}
            />
          ))}
        </ul>
      )}

      {canAttach && (
        <>
          {picker.editing ? (
            <div className="attachment-picker">
              <label>
                <span>Choose a file</span>
                <input
                  ref={inputRef}
                  type="file"
                  disabled={upload.isPending}
                  onChange={send}
                />
              </label>
              <button
                type="button"
                className="secondary-button"
                onClick={picker.close}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              ref={triggerRef}
              type="button"
              className="disclosure-button"
              onClick={picker.open}
            >
              <span aria-hidden="true">+</span> Attach file
            </button>
          )}
          {/* The server decides what a file is allowed to be — its sniffed
              type, its size — so this is where a reader finds out why a
              document was refused. The API's own sentence is the message:
              "Unsupported file type", "File exceeds the ... byte upload
              limit". */}
          {upload.isPending && <p className="meta-row">Uploading...</p>}
          {upload.isError && <p className="error">{upload.error.message}</p>}
        </>
      )}
    </div>
  );
}

function AttachmentRow({
  attachment,
  access,
  onDelete,
}: {
  attachment: Attachment;
  access: Access;
  onDelete: () => void;
}) {
  return (
    <li className="attachment-row">
      {/* `download` asks the browser to save rather than navigate; the
          response says so too (`uploads.download_headers`), which is what
          makes it true for a middle-click as well. */}
      <a href={attachmentDownloadPath(attachment.id)} download>
        {attachment.filename}
      </a>
      <span className="meta-row">
        {formatBytes(attachment.byte_size)} | {attachment.uploader_name}
      </span>
      {access.canChangeItem(attachment.uploaded_by) && (
        <button type="button" className="danger-button" onClick={onDelete}>
          Delete
        </button>
      )}
    </li>
  );
}
