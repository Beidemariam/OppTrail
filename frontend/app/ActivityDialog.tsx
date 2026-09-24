"use client";

import { useState } from "react";

import {
  activityActor,
  activitySentence,
  type ActivityEvent,
} from "../lib/activity";
import {
  noteVersionFields,
  opportunityVersionFields,
  timelineEntryVersionFields,
} from "../lib/domain";
import {
  useActivity,
  useNoteVersions,
  useOpportunityVersions,
  useTimelineEntryVersions,
} from "../lib/queries";
import { formatTimestamp } from "../lib/time";
import { Modal } from "./Modal";
import { VersionDiff } from "./VersionChanges";

/**
 * One history per opportunity (milestone 3.0, completed by 3.1c).
 *
 * The history of a deal used to be three screens that never met: the system
 * entries inside the timeline, the audit log folded into the sharing panel,
 * and a per-item history dialog for every edit. 3.0 merged the rows
 * (`backend/app/activity.py`); 3.1c removed the other two destinations by
 * giving an edit row here the before/after and the way back that only the
 * History dialog used to offer (D-116, D-121).
 *
 * **Offered to every role.** The rows a reader gets are the ones their role
 * may already see — system entries for anyone with access, the audit and
 * version halves for the owner — so an edit row appearing at all means the
 * reader owns this opportunity, which is why the Restore control inside one
 * needs no second permission check of its own.
 */
export function ActivityButton({ opportunityId }: { opportunityId: number }) {
  const [open, setOpen] = useState(false);
  const query = useActivity(opportunityId, open);

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
        <Modal
          label="Activity and history"
          title="Activity and history"
          onClose={() => setOpen(false)}
        >
          <p className="history-lead">
            Everything that has happened to this opportunity, oldest first: what
            the system recorded, what was edited, and what was deleted or
            restored. You see the events your role can read, and an edit opens
            to show what it changed.
          </p>
          {query.isError && <p className="error">{query.error.message}</p>}
          {query.isPending && <p className="status">Loading activity...</p>}
          {query.data &&
            (query.data.length === 0 ? (
              <p className="empty-state">Nothing has happened here yet.</p>
            ) : (
              <ol className="activity-list">
                {query.data.map((event) => (
                  <li className="activity-event" key={event.id}>
                    <p className="activity-sentence">
                      <strong>{activityActor(event)}</strong>{" "}
                      {activitySentence(event)}
                    </p>
                    <p className="meta-row">
                      {formatTimestamp(event.occurred_at)}
                    </p>
                    {event.detail.source === "version" && (
                      <EditDetails detail={event.detail} />
                    )}
                  </li>
                ))}
              </ol>
            ))}
        </Modal>
      )}
    </>
  );
}

type EditDetail = Extract<ActivityEvent["detail"], { source: "version" }>;

/**
 * An edit row, opened.
 *
 * A disclosure button rather than `<details>`: the open state is also what
 * enables the read behind it, so it is React's rather than the element's.
 */
function EditDetails({ detail }: { detail: EditDetail }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="activity-changes">
      <button
        type="button"
        className="link-button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? "Hide what changed" : "What changed"}
      </button>
      {open && <EditDiff detail={detail} />}
    </div>
  );
}

/**
 * Which history this edit is in. Three branches because each kind has its own
 * version shape, its own field declarations and its own read — the one thing
 * `lib/domain.ts` cannot collapse into a single table.
 */
function EditDiff({ detail }: { detail: EditDetail }) {
  if (detail.target === "opportunity") {
    return (
      <VersionDiff
        target="opportunity"
        targetId={detail.target_id}
        versionNumber={detail.version_number}
        fields={opportunityVersionFields}
        useVersions={useOpportunityVersions}
      />
    );
  }
  if (detail.target === "timeline_entry") {
    return (
      <VersionDiff
        target="timeline_entry"
        targetId={detail.target_id}
        versionNumber={detail.version_number}
        fields={timelineEntryVersionFields}
        useVersions={useTimelineEntryVersions}
      />
    );
  }
  return (
    <VersionDiff
      target="note"
      targetId={detail.target_id}
      versionNumber={detail.version_number}
      fields={noteVersionFields}
      useVersions={useNoteVersions}
    />
  );
}
