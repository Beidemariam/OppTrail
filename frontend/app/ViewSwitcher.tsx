"use client";

import { opportunityViews, type OpportunityView } from "../lib/domain";

/**
 * Which renderer draws the opportunities (milestone 2.7, four of them since
 * 2.8).
 *
 * The choice is part of the URL-serialized view state, so it is linkable,
 * survives a reload and is what a saved view stores alongside its filters
 * (`lib/viewState.ts`). The list itself lives in `lib/domain.ts` beside the
 * `OpportunityView` type, so adding a renderer is one edit rather than two
 * that can disagree.
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
      {opportunityViews.map((candidate) => (
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
