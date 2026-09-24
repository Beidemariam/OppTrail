"use client";

import type { UseQueryResult } from "@tanstack/react-query";

import type { ActivityEditTarget } from "../lib/activity";
import {
  versionChanges,
  type VersionChange,
  type VersionField,
} from "../lib/domain";
import { useRestoreVersion } from "../lib/queries";
import { useToasts } from "./Toasts";

/**
 * What one edit changed, and the way back to what it said before
 * (milestone 3.1c, D-116).
 *
 * This is the half of the old per-item History dialog worth keeping. That
 * dialog was a third destination beside the activity log and the audit log
 * (D-121); what it could answer that the feed could not was "what did this
 * field say before", so that answer moved into the feed's own rows and the
 * destination went.
 *
 * A version is a snapshot of every editable field
 * (`backend/app/versioning.py`), so which fields exist and how each one reads
 * is all that differs between an opportunity, an entry and a note.
 * `lib/domain.ts` declares that per kind and `versionChanges` compares two
 * snapshots without knowing which kind it holds — which is why the currency
 * still reaches the money formatter here and would not if the server sent
 * each changed column on its own.
 */
export interface VersionRow {
  id: number;
  version_number: number;
}

export function VersionDiff<VersionT extends VersionRow>({
  target,
  targetId,
  versionNumber,
  fields,
  useVersions,
}: {
  target: ActivityEditTarget;
  targetId: number;
  /** The version this edit produced; the one before it is what it replaced. */
  versionNumber: number;
  fields: VersionField<VersionT>[];
  useVersions: (
    id: number,
    enabled: boolean,
  ) => UseQueryResult<VersionT[], Error>;
}) {
  // Fetched when the row is expanded, not when the feed is drawn: an
  // opportunity with forty edits would otherwise open its log with forty
  // requests (the rule the History dialog already followed).
  const query = useVersions(targetId, true);

  if (query.isError) {
    return <p className="error">{query.error.message}</p>;
  }
  if (query.isPending) {
    return <p className="status">Loading what changed...</p>;
  }

  const version = query.data.find(
    (candidate) => candidate.version_number === versionNumber,
  );
  const previous = query.data.find(
    (candidate) => candidate.version_number === versionNumber - 1,
  );
  if (!version || !previous) {
    // By construction both are recorded: the feed builds an edit row by
    // joining a version to the one before it (`backend/app/activity.py`).
    // The branch exists because `find` cannot know that, not because the
    // history is expected to have a hole in it.
    return null;
  }

  return (
    <>
      <VersionFields changes={versionChanges(fields, version, previous)} />
      <RestoreVersion
        target={target}
        targetId={targetId}
        versionNumber={previous.version_number}
      />
    </>
  );
}

/**
 * Putting the earlier version back.
 *
 * Offered on the version this edit *replaced*, not on the one it wrote: every
 * recorded version except the current one is the "before" of exactly one edit
 * row, so this is how each of them is reached, including version 1 — the
 * state the thing was created in. Restoring is itself recorded as an edit, so
 * it can be undone by restoring again and nothing in the history is lost
 * (D-120).
 */
function RestoreVersion({
  target,
  targetId,
  versionNumber,
}: {
  target: ActivityEditTarget;
  targetId: number;
  versionNumber: number;
}) {
  const restore = useRestoreVersion(target, targetId);
  const toast = useToasts();

  return (
    <p className="version-restore">
      <button
        type="button"
        className="secondary-button"
        disabled={restore.isPending}
        onClick={() =>
          restore.mutate(versionNumber, {
            onSuccess: () =>
              toast({
                message: `Restored version ${versionNumber}. The restore is recorded as an edit of its own.`,
              }),
            onError: (error) =>
              toast({ message: error.message, tone: "error" }),
          })
        }
      >
        Restore version {versionNumber}
      </button>
    </p>
  );
}

export function VersionFields({ changes }: { changes: VersionChange[] }) {
  if (changes.length === 0) {
    return <p className="empty-state">Saved with no field changed.</p>;
  }

  return (
    <dl className="history-fields">
      {changes.map((change) => (
        <div className="history-change" key={change.label}>
          <dt>{change.label}</dt>
          <dd>
            <span className="history-before">{change.before}</span>{" "}
            {/* The word rather than an arrow glyph: it is what a screen
                reader should say, and it survives a font without one. The
                spaces around it are the ones a reader hears -- CSS margin
                separates the boxes and leaves the text content running
                together. */}
            <span className="history-arrow">to</span>{" "}
            <span className="history-after">{change.after}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
