"use client";

import { useState } from "react";

import { stages, type Opportunity } from "../lib/domain";
import { canManageOpportunity } from "../lib/permissions";

type Stage = (typeof stages)[number];

/**
 * Replaces the filter bar while a bulk selection is live (`docs/UX.md`,
 * milestone 2.4c). Presentational like `OpportunityFilterBar`: the dashboard
 * owns the request (`useBulkOpportunityAction`) and the toast that reports
 * its outcome.
 *
 * Only "change stage" and "delete" are offered — D-070 is why the action bar
 * does not also carry "assign owner", "add to view" and export, which
 * `docs/UX.md` lists but which have no single-item capability to reuse.
 */
export function BulkActionBar({
  selected,
  onClear,
  onChangeStage,
  onDelete,
  pending,
}: {
  selected: Opportunity[];
  onClear: () => void;
  onChangeStage: (stage: Stage) => void;
  onDelete: () => void;
  pending: boolean;
}) {
  const [stage, setStage] = useState<Stage>(stages[0]);
  // The server enforces this per item regardless (`docs/UX.md`: "report
  // per-item failures"), but the UI should not offer an action every
  // selected row would be refused — the same rule the per-card Edit/Delete
  // buttons already follow (`lib/permissions.ts`'s `canManageOpportunity`).
  const allOwned =
    selected.length > 0 &&
    selected.every((opportunity) =>
      canManageOpportunity(opportunity.current_user_role),
    );

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
        <p>Change stage and delete are limited to opportunities you own.</p>
      )}
    </div>
  );
}
