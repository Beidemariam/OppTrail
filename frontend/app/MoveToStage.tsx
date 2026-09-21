"use client";

import { stages, type Opportunity, type Stage } from "../lib/domain";

/**
 * The keyboard and pointer alternative to dragging a card across the board
 * (milestone 2.7).
 *
 * `docs/DESIGN-SYSTEM.md` names this as the requirement most likely to be
 * skipped: drag-and-drop needs a move-to-stage control or the board is
 * unusable without a mouse. It doubles as the stage display in the list view,
 * where the row has no column to drop into.
 *
 * Offered only to the owner, because changing an opportunity's fields is
 * owner-only (`lib/permissions.ts`, `backend/app/permissions.py`).
 */
export function MoveToStage({
  opportunity,
  onMove,
}: {
  opportunity: Opportunity;
  onMove: (opportunity: Opportunity, stage: Stage) => void;
}) {
  return (
    <label className="move-to-stage">
      <span className="visually-hidden">Move {opportunity.name} to stage</span>
      <select
        value={opportunity.stage}
        onChange={(event) => onMove(opportunity, event.target.value as Stage)}
      >
        {stages.map((stage) => (
          <option key={stage} value={stage}>
            {stage}
          </option>
        ))}
      </select>
    </label>
  );
}
