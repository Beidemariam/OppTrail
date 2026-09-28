"use client";

import { FormEvent, useState } from "react";

import {
  emptyTimelineFilters,
  entryTypes,
  timelineFiltersApplied,
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
 *
 * Each control carries a visible name beside its `aria-label` for the reason
 * `OpportunityFilterBar` explains (milestone 2.13, **D-082**): a row of
 * unlabelled dropdowns is a control the reader cannot identify.
 *
 * **Collapsed until it is asked for** (milestone 3.7). Six always-visible
 * controls and the composer beneath them put the first timeline entry 930px
 * down a 1000px viewport, so the thing this screen is about opened below the
 * fold (D-136 finding 3). The disclosure is the pattern `docs/UX.md` asks for
 * and `app/RichTextEditor.tsx`'s `Composer` already uses for notes and
 * comments. Two things ride on it:
 *
 * - **The trigger says what is in force**, not just "Filters": the reading
 *   order always applies and the rest may arrive from a URL, so a reader who
 *   never opens this still learns why the timeline is ordered the way it is.
 *   That is the visible half of D-137.
 * - **It opens itself when something is applied**, so a shared or reloaded
 *   link shows its own filters rather than hiding them behind a summary.
 */
export function TimelineFilterBar({
  filters,
  onApply,
}: {
  filters: TimelineFilters;
  onApply: (filters: TimelineFilters) => void;
}) {
  const applied = timelineFiltersApplied(filters);
  const [appliedFilters, setAppliedFilters] = useState(filters);
  const [draft, setDraft] = useState<TimelineFilters>(filters);
  const [open, setOpen] = useState(applied > 0);
  if (filters !== appliedFilters) {
    setAppliedFilters(filters);
    setDraft(filters);
    // A filter arriving from the URL, the back button or a saved view opens
    // the bar: what is filtering the timeline has to be visible where it is
    // changed, not only summarized.
    if (applied > 0) {
      setOpen(true);
    }
  }

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onApply(draft);
  }

  function clear() {
    setDraft(emptyTimelineFilters);
    onApply(emptyTimelineFilters);
  }

  if (!open) {
    return (
      <p className="filter-summary">
        <button
          type="button"
          className="disclosure-button"
          aria-expanded={false}
          onClick={() => setOpen(true)}
        >
          <span aria-hidden="true">+</span> Filter and order
        </button>
        <span className="meta-row">{summary(filters, applied)}</span>
      </p>
    );
  }

  return (
    <form className="filter-bar" onSubmit={apply}>
      <p className="filter-note">
        <button
          type="button"
          className="disclosure-button"
          aria-expanded={true}
          onClick={() => setOpen(false)}
        >
          <span aria-hidden="true">-</span> Filter and order
        </button>
      </p>
      <label className="filter-field grow">
        Keyword
        <input
          aria-label="Filter the timeline by keyword"
          placeholder="Anything written in an entry"
          value={draft.q}
          onChange={(event) => setDraft({ ...draft, q: event.target.value })}
        />
      </label>
      <label className="filter-field">
        Type
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
      </label>
      <label className="filter-field">
        From
        <input
          aria-label="Show entries from"
          type="datetime-local"
          value={draft.from}
          onChange={(event) => setDraft({ ...draft, from: event.target.value })}
        />
      </label>
      <label className="filter-field">
        Up to
        <input
          aria-label="Show entries up to"
          type="datetime-local"
          value={draft.to}
          onChange={(event) => setDraft({ ...draft, to: event.target.value })}
        />
      </label>
      <label className="filter-field">
        Author ID
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
      </label>
      <label className="filter-field">
        Order
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
      </label>
      <button className="primary-button" type="submit">
        Filter
      </button>
      <button className="secondary-button" type="button" onClick={clear}>
        Clear
      </button>
    </form>
  );
}

/** What the collapsed bar says is in force. The order is named in the same
 * words as the control that sets it, so opening the bar confirms rather than
 * translates. */
function summary(filters: TimelineFilters, applied: number): string {
  const order = filters.order === "asc" ? "Oldest first" : "Newest first";
  const others =
    filters.order === emptyTimelineFilters.order ? applied : applied - 1;
  if (others === 0) {
    return order;
  }
  return `${order}, ${others} filter${others === 1 ? "" : "s"} applied`;
}
