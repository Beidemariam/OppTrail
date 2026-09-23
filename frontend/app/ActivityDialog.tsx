"use client";

import { useState } from "react";

import { activityActor, activitySentence } from "../lib/activity";
import { useActivity } from "../lib/queries";
import { formatTimestamp } from "../lib/time";
import { Modal } from "./Modal";

/**
 * One activity log per opportunity (milestone 3.0, D-101).
 *
 * The history of a deal used to be three screens that never met: the system
 * entries inside the timeline, the audit log folded into the sharing panel,
 * and a per-item history dialog for every edit. This is the one place that
 * answers "who did what when" for the whole opportunity, over the same rows
 * (`backend/app/activity.py`) rather than over anything new.
 *
 * **Offered to every role**, unlike the History button beside it. The rows a
 * reader gets are the ones their role may already see — system entries for
 * anyone with access, the audit and version halves for the owner — so the
 * answer to "why is this shorter for me" is the same rule that governs the
 * screens it merges, and the server is what applies it.
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
        Activity
      </button>
      {open && (
        <Modal
          label="Activity log"
          title="Activity log"
          onClose={() => setOpen(false)}
        >
          <p className="history-lead">
            Everything that has happened to this opportunity, oldest first: what
            the system recorded, what was edited, and what was deleted or
            restored. You see the events your role can read.
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
                  </li>
                ))}
              </ol>
            ))}
        </Modal>
      )}
    </>
  );
}
