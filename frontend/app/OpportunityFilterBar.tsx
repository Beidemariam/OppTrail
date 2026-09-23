"use client";

import { FormEvent, useState, type RefObject } from "react";

import {
  emptyOpportunityViewState,
  pinnedIds,
  sortFields,
  stages,
  type OpportunityViewState,
} from "../lib/domain";

/**
 * The opportunity board's filter/sort bar (milestone 2.2).
 *
 * Controlled, with the draft re-derived from `state` during render when it
 * changes — the same pattern `TimelineFilterBar` uses, so a value arriving
 * from the URL, the back button or a saved view updates the form without an
 * effect or a remount.
 *
 * Every control carries a visible name as well as its `aria-label` (milestone
 * 2.13, **D-082**). The reviewer's note was that "the filter and sort windows
 * are just a series of windows and you wouldn't know which one is which by
 * looking at them" — five unlabelled dropdowns in a row, each legible only to
 * a screen reader. The visible word is the short one and the `aria-label`
 * stays the longer sentence that distinguishes this bar from the timeline's,
 * which keeps both bars addressable while the screen says what it is.
 */
export function OpportunityFilterBar({
  state,
  keywordRef,
  onApply,
}: {
  state: OpportunityViewState;
  /** Where `/` puts the cursor (milestone 2.4a). */
  keywordRef?: RefObject<HTMLInputElement | null>;
  onApply: (state: OpportunityViewState) => void;
}) {
  const [appliedState, setAppliedState] = useState(state);
  const [draft, setDraft] = useState<OpportunityViewState>(state);
  if (state !== appliedState) {
    setAppliedState(state);
    setDraft(state);
  }

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onApply(draft);
  }

  function clear() {
    setDraft(emptyOpportunityViewState);
    onApply(emptyOpportunityViewState);
  }

  const pinned = pinnedIds(state.ids);

  return (
    <form className="filter-bar" onSubmit={apply}>
      <label className="filter-field grow">
        Keyword
        <input
          ref={keywordRef}
          aria-label="Filter opportunities by keyword"
          placeholder="Name, account or owner"
          value={draft.q}
          onChange={(event) => setDraft({ ...draft, q: event.target.value })}
        />
      </label>
      <label className="filter-field">
        Stage
        <select
          aria-label="Filter by stage"
          value={draft.stage}
          onChange={(event) =>
            setDraft({ ...draft, stage: event.target.value })
          }
        >
          <option value="">All stages</option>
          {stages.map((stage) => (
            <option key={stage} value={stage}>
              {stage}
            </option>
          ))}
        </select>
      </label>
      <label className="filter-field">
        Stalled
        <select
          aria-label="Filter by stalled status"
          value={draft.stalled}
          onChange={(event) =>
            setDraft({
              ...draft,
              stalled: event.target.value as OpportunityViewState["stalled"],
            })
          }
        >
          <option value="">Stalled or not</option>
          <option value="true">Stalled only</option>
          <option value="false">Not stalled</option>
        </select>
      </label>
      <label className="filter-field">
        Sort by
        <select
          aria-label="Sort by"
          value={draft.sortField}
          onChange={(event) =>
            setDraft({
              ...draft,
              sortField: event.target
                .value as OpportunityViewState["sortField"],
            })
          }
        >
          {sortFields.map((field) => (
            <option key={field.value} value={field.value}>
              {field.label}
            </option>
          ))}
        </select>
      </label>
      <label className="filter-field">
        Direction
        <select
          aria-label="Sort direction"
          value={draft.sortDirection}
          onChange={(event) =>
            setDraft({
              ...draft,
              sortDirection: event.target.value === "asc" ? "asc" : "desc",
            })
          }
        >
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </label>
      <button className="primary-button" type="submit">
        Apply
      </button>
      <button className="secondary-button" type="button" onClick={clear}>
        Clear
      </button>
      {/* A view can also filter to a pinned selection (milestone 3.0a,
          D-106). It has no control of its own — it is written by the action
          bar's "add to view" and arrives with the view — so the bar says it
          is in force and offers the way out, which is the same job the
          applied-view line does for the rest of a saved view. */}
      {pinned && (
        <p className="field-hint filter-note">
          Showing {pinned.size}{" "}
          {pinned.size === 1 ? "pinned opportunity" : "pinned opportunities"}{" "}
          from a saved view.
          <button
            className="secondary-button compact-button"
            type="button"
            onClick={() => {
              setDraft({ ...draft, ids: "" });
              onApply({ ...state, ids: "" });
            }}
          >
            Show all
          </button>
        </p>
      )}
    </form>
  );
}
