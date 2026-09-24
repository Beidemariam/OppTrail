"use client";

import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";

import {
  versionChanges,
  type VersionChange,
  type VersionField,
} from "../lib/domain";
import { formatTimestamp } from "../lib/time";
import { Modal } from "./Modal";

/**
 * Edit history, for the three things this app lets a reader change
 * (milestone 2.10; `AGENTS.md` invariant 8).
 *
 * One screen rather than three. A version is a snapshot of every editable
 * field (`backend/app/versioning.py`), so what differs between an
 * opportunity, an entry and a note is only which fields exist and how each
 * one reads: `lib/domain.ts` declares that per kind, `versionChanges`
 * compares two versions without knowing which kind it holds, and the hook
 * that fetches them arrives as a prop rather than being chosen here.
 *
 * **Owner-only**, matching the audit log (D-096). The call sites render the
 * button only for the opportunity's owner and the server refuses everyone
 * else, so one rule covers all three and a reader never has to work out why
 * one item offers history and the next does not.
 */
export interface VersionRow {
  id: number;
  version_number: number;
  editor_name: string;
  created_at: string;
}

export function HistoryButton<VersionT extends VersionRow>({
  title,
  fields,
  itemId,
  useVersions,
}: {
  title: string;
  fields: VersionField<VersionT>[];
  itemId: number;
  /**
   * The read for this kind (`lib/queries.ts`). Called unconditionally with
   * `enabled` bound to the dialog being open, so opening a timeline of forty
   * entries costs no history requests and opening one dialog costs one.
   */
  useVersions: (
    id: number,
    enabled: boolean,
  ) => UseQueryResult<VersionT[], Error>;
}) {
  const [open, setOpen] = useState(false);
  const query = useVersions(itemId, open);

  return (
    <>
      <button
        type="button"
        className="secondary-button"
        onClick={() => setOpen(true)}
      >
        History
      </button>
      {open && (
        <Modal label={title} title={title} onClose={() => setOpen(false)}>
          <p className="history-lead">
            Every version since this was created, oldest first. The first is
            what it said when it was created; each one after it lists only what
            that edit changed.
          </p>
          <HistoryBody fields={fields} query={query} />
        </Modal>
      )}
    </>
  );
}

function HistoryBody<VersionT extends VersionRow>({
  fields,
  query,
}: {
  fields: VersionField<VersionT>[];
  query: UseQueryResult<VersionT[], Error>;
}) {
  if (query.isError) {
    return <p className="error">{query.error.message}</p>;
  }
  if (query.isPending) {
    return <p className="status">Loading history...</p>;
  }
  if (query.data.length === 0) {
    return <p className="empty-state">No history recorded for this item.</p>;
  }

  return (
    <ol className="history-list">
      {query.data.map((version, index) => (
        <li className="history-version" key={version.id}>
          <p className="meta-row">
            {/* A single row with nothing to compare against reads as broken
                rather than complete without saying what it is (milestone
                3.1a, D-115): the value as first recorded, not an edit. */}
            {index === 0
              ? `Version ${version.version_number} — recorded when this was created`
              : `Version ${version.version_number}`}{" "}
            | {version.editor_name} | {formatTimestamp(version.created_at)}
          </p>
          <VersionFields
            changes={versionChanges(
              fields,
              version,
              index === 0 ? undefined : query.data[index - 1],
            )}
          />
        </li>
      ))}
    </ol>
  );
}

function VersionFields({ changes }: { changes: VersionChange[] }) {
  if (changes.length === 0) {
    return <p className="empty-state">Saved with no field changed.</p>;
  }

  return (
    <dl className="history-fields">
      {changes.map((change) => (
        <div className="history-change" key={change.label}>
          <dt>{change.label}</dt>
          <dd>
            {change.before !== null && (
              <>
                <span className="history-before">{change.before}</span>{" "}
                {/* The word rather than an arrow glyph: it is what a screen
                    reader should say, and it survives a font without one. The
                    spaces around it are the ones a reader hears -- CSS margin
                    separates the boxes and leaves the text content running
                    together. */}
                <span className="history-arrow">to</span>{" "}
              </>
            )}
            <span className="history-after">{change.after}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
