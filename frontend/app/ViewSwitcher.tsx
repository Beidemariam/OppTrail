"use client";

import type { OpportunityView } from "../lib/domain";

const views = [
  { value: "board", label: "Board" },
  { value: "list", label: "List" },
] as const;

/**
 * Which renderer draws the opportunities (milestone 2.7).
 *
 * The choice is part of the URL-serialized view state, so it is linkable,
 * survives a reload and is what a saved view stores alongside its filters
 * (`lib/viewState.ts`). Table and calendar (2.8) are two more entries here.
 */
export function ViewSwitcher({
  view,
  onChange,
}: {
  view: OpportunityView;
  onChange: (view: OpportunityView) => void;
}) {
  return (
    <div className="segmented" role="group" aria-label="View">
      {views.map((candidate) => (
        <button
          key={candidate.value}
          type="button"
          className={candidate.value === view ? "active" : ""}
          aria-pressed={candidate.value === view}
          onClick={() => onChange(candidate.value)}
        >
          {candidate.label}
        </button>
      ))}
    </div>
  );
}
