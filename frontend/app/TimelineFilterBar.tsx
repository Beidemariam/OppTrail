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
 * The typed draft and the applied set are still separate — the applied set is
 * what changes the URL and the timeline query — but the draft now
 * initializes from, and re-syncs to, the `filters` prop: a value can arrive
 * here from typing and pressing Filter, from the back button, or from
 * applying a saved view. Re-deriving state from a changed prop during render
 * (rather than in an effect) is the pattern React itself recommends for this —
 * it re-renders before paint instead of committing a stale frame first.
 */
export function TimelineFilterBar({
  filters,
  onApply,
}: {
  filters: TimelineFilters;
  onApply: (filters: TimelineFilters) => void;
}) {
  const [appliedFilters, setAppliedFilters] = useState(filters);
  const [draft, setDraft] = useState<TimelineFilters>(filters);
  if (filters !== appliedFilters) {
    setAppliedFilters(filters);
    setDraft(filters);
  }

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
      <select
        aria-label="Timeline reading order"
        value={draft.order}
        onChange={(event) =>
          setDraft({
            ...draft,
            order: event.target.value === "desc" ? "desc" : "asc",
          })
        }
      >
        <option value="asc">Oldest first</option>
        <option value="desc">Newest first</option>
      </select>
      <button className="primary-button" type="submit">
        Filter
      </button>
      <button className="secondary-button" type="button" onClick={clear}>
        Clear
      </button>
    </form>
  );
}
