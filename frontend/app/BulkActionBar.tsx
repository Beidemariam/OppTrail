"use client";

import { useState } from "react";

import { savedViewLabel, stages, type Opportunity } from "../lib/domain";
import { canManageOpportunity } from "../lib/permissions";
import { useSavedViews, useSession } from "../lib/queries";

type Stage = (typeof stages)[number];

/**
 * Replaces the filter bar while a bulk selection is live (`docs/UX.md`,
 * milestone 2.4c, completed in 3.0a). Presentational like
 * `OpportunityFilterBar`: the dashboard owns the requests
 * (`useBulkOpportunityAction`) and the toasts that report their outcomes.
 *
 * All five of `docs/UX.md`'s actions are here, and they are gated by three
 * different rules rather than one, because they write to three different
 * things:
 *
 * - **Change stage, assign owner and delete write to the opportunity**, so
 *   they are offered only when the whole selection is owned — the same
 *   `canManageOpportunity` gate the per-card Edit and Delete follow. The
 *   server checks per item regardless (`docs/UX.md`: "report per-item
 *   failures"); this is about not offering an action every row would refuse.
 * - **Add to view writes to the reader's own saved view**, not to the
 *   opportunities, so anything the reader can see can be pinned (D-106) and
 *   the control is disabled only when they have no view of their own to add
 *   to.
 * - **Export reads**, so it is a plain link like the per-opportunity exports
 *   on the timeline (D-107) — no mutation, no pending state, and the browser
 *   downloads it.
 */
export function BulkActionBar({
  selected,
  onClear,
  onChangeStage,
  onAssignOwner,
  onAddToView,
  onDelete,
  pending,
}: {
  selected: Opportunity[];
  onClear: () => void;
  onChangeStage: (stage: Stage) => void;
  onAssignOwner: (email: string) => void;
  onAddToView: (viewId: number) => void;
  onDelete: () => void;
  pending: boolean;
}) {
  const session = useSession();
  const savedViews = useSavedViews("opportunities");
  const [stage, setStage] = useState<Stage>(stages[0]);
  const [newOwnerEmail, setNewOwnerEmail] = useState("");
  const [viewId, setViewId] = useState("");

  // The server enforces this per item regardless (`docs/UX.md`: "report
  // per-item failures"), but the UI should not offer an action every
  // selected row would be refused — the same rule the per-card Edit/Delete
  // buttons already follow (`lib/permissions.ts`'s `canManageOpportunity`).
  const allOwned =
    selected.length > 0 &&
    selected.every((opportunity) =>
      canManageOpportunity(opportunity.current_user_role),
    );

  // Only the reader's own views: adding to a colleague's shared view would
  // change what every signed-in reader sees through it, which is why the
  // route refuses it (creator-only write, D-106).
  const ownViews = (savedViews.data ?? []).filter(
    (view) => view.created_by === session.data?.id,
  );
  const ids = selected.map((opportunity) => opportunity.id).join(",");

  return (
    <div className="bulk-action-bar" role="toolbar" aria-label="Bulk actions">
      <span>{selected.length} selected</span>
      <select
        aria-label="Change stage to"
        value={stage}
        onChange={(event) => setStage(event.target.value as Stage)}
        disabled={!allOwned}
      >
        {stages.map((candidate) => (
          <option key={candidate} value={candidate}>
            {candidate}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="secondary-button"
        disabled={!allOwned || pending}
        onClick={() => onChangeStage(stage)}
      >
        Change stage
      </button>

      <input
        type="email"
        aria-label="Assign owner by email"
        placeholder="new.owner@example.com"
        value={newOwnerEmail}
        disabled={!allOwned}
        onChange={(event) => setNewOwnerEmail(event.target.value)}
      />
      <button
        type="button"
        className="secondary-button"
        disabled={!allOwned || pending || !newOwnerEmail.trim()}
        onClick={() => onAssignOwner(newOwnerEmail.trim())}
      >
        Assign owner
      </button>

      <select
        aria-label="Add to saved view"
        value={viewId}
        disabled={ownViews.length === 0}
        onChange={(event) => setViewId(event.target.value)}
      >
        <option value="">Choose one of your views...</option>
        {ownViews.map((view) => (
          <option key={view.id} value={view.id}>
            {savedViewLabel(view, session.data?.id)}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="secondary-button"
        disabled={!viewId || pending}
        onClick={() => onAddToView(Number(viewId))}
      >
        Add to view
      </button>

      {(["csv", "json"] as const).map((format) => (
        <a
          key={format}
          className="secondary-button"
          href={`/api/v2/opportunities/export/${format}?ids=${ids}`}
        >
          Export {format.toUpperCase()}
        </a>
      ))}

      <button
        type="button"
        className="danger-button"
        disabled={!allOwned || pending}
        onClick={onDelete}
      >
        Delete
      </button>
      <button type="button" className="secondary-button" onClick={onClear}>
        Clear selection
      </button>
      {!allOwned && (
        <p>
          Change stage, assign owner and delete are limited to opportunities you
          own.
        </p>
      )}
      {ownViews.length === 0 && (
        <p>Save a view of your own to add opportunities to it.</p>
      )}
    </div>
  );
}
