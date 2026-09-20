"use client";

import { FormEvent, useState } from "react";

import {
  emptyTimelineFilters,
  entryTypes,
  type TimelineFilters,
} from "../lib/domain";

/**
 * The timeline's filter bar.
 *
 * The typed values and the applied ones are separate: the applied set is part
 * of the timeline's query key, so it asks the API exactly once per Filter
 * press rather than on every keystroke. Milestone 2.2 moves the applied set
 * into the URL.
 */
export function TimelineFilterBar({
  onApply,
}: {
  onApply: (filters: TimelineFilters) => void;
}) {
  const [draft, setDraft] = useState<TimelineFilters>(emptyTimelineFilters);

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onApply(draft);
  }

  function clear() {
    setDraft(emptyTimelineFilters);
    onApply(emptyTimelineFilters);
  }

  return (
    <form className="filter-bar" onSubmit={apply}>
      <input
        aria-label="Filter the timeline by keyword"
        placeholder="Keyword"
        value={draft.q}
        onChange={(event) => setDraft({ ...draft, q: event.target.value })}
      />
      <select
        aria-label="Filter the timeline by entry type"
        value={draft.type}
        onChange={(event) => setDraft({ ...draft, type: event.target.value })}
      >
        <option value="">All types</option>
        {entryTypes.map((entryType) => (
          <option key={entryType.value} value={entryType.value}>
            {entryType.label}
          </option>
        ))}
      </select>
      <input
        aria-label="Show entries from"
        type="datetime-local"
        value={draft.from}
        onChange={(event) => setDraft({ ...draft, from: event.target.value })}
      />
      <input
        aria-label="Show entries up to"
        type="datetime-local"
        value={draft.to}
        onChange={(event) => setDraft({ ...draft, to: event.target.value })}
      />
      <input
        aria-label="Filter the timeline by author id"
        type="number"
        min="1"
        placeholder="Author ID"
        value={draft.author_id}
        onChange={(event) =>
          setDraft({ ...draft, author_id: event.target.value })
        }
      />
      <button className="primary-button" type="submit">
        Filter
      </button>
      <button className="secondary-button" type="button" onClick={clear}>
        Clear
      </button>
    </form>
  );
}
