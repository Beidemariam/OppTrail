"use client";

import { FormEvent, useState, type RefObject } from "react";

import {
  emptyOpportunityViewState,
  stages,
  type OpportunityViewState,
} from "../lib/domain";

const sortFields = [
  { value: "updated_at", label: "Last activity" },
  { value: "value", label: "Value" },
  { value: "expected_close_date", label: "Close date" },
  { value: "name", label: "Name" },
] as const;

/**
 * The opportunity board's filter/sort bar (milestone 2.2).
 *
 * Controlled, with the draft re-derived from `state` during render when it
 * changes — the same pattern `TimelineFilterBar` uses, so a value arriving
 * from the URL, the back button or a saved view updates the form without an
 * effect or a remount.
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

  return (
    <form className="filter-bar" onSubmit={apply}>
      <input
        ref={keywordRef}
        aria-label="Filter opportunities by keyword"
        placeholder="Name, account or owner"
        value={draft.q}
        onChange={(event) => setDraft({ ...draft, q: event.target.value })}
      />
      <select
        aria-label="Filter by stage"
        value={draft.stage}
        onChange={(event) => setDraft({ ...draft, stage: event.target.value })}
      >
        <option value="">All stages</option>
        {stages.map((stage) => (
          <option key={stage} value={stage}>
            {stage}
          </option>
        ))}
      </select>
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
      <select
        aria-label="Sort by"
        value={draft.sortField}
        onChange={(event) =>
          setDraft({
            ...draft,
            sortField: event.target.value as OpportunityViewState["sortField"],
          })
        }
      >
        {sortFields.map((field) => (
          <option key={field.value} value={field.value}>
            {field.label}
          </option>
        ))}
      </select>
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
      <button className="primary-button" type="submit">
        Apply
      </button>
      <button className="secondary-button" type="button" onClick={clear}>
        Clear
      </button>
    </form>
  );
}
