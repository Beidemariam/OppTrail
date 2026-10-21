"use client";

import { FormEvent, useState, type RefObject } from "react";

import {
  appliedOpportunityFilters,
  customFilterState,
  customFilters,
  emptyOpportunityViewState,
  pinnedIds,
  sortFields,
  stages,
  type CustomField,
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
 * **Collapsed until it is asked for** (R.1, decision 3A), the way the
 * timeline's bar has been since 3.7 and for the same measured reason: eight
 * always-visible controls were 77px at 1440, 144px at 1024 and 320px at 420,
 * and they grew by a row for every custom field anybody defined — unbounded,
 * above the board the screen is about. A shut panel is not a silent one: what
 * is in force is drawn as a chip each, and every chip removes its own filter
 * (`appliedOpportunityFilters`). Whether it is open is the screen's state
 * rather than this component's: a filter arriving from a URL or a saved view
 * opens it, so a shared link shows its own filters rather than hiding them
 * behind a summary — while removing a chip leaves the reader in the strip they
 * were working in. `DashboardPage` is where those two cases are told apart.
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
  open,
  onOpenChange,
  fields = [],
}: {
  state: OpportunityViewState;
  /** Where `/` puts the cursor (milestone 2.4a). */
  keywordRef?: RefObject<HTMLInputElement | null>;
  onApply: (state: OpportunityViewState) => void;
  /** Whether the controls are showing. Owned by the screen rather than by this
   * component since R.1, because `/` has to be able to open them before it can
   * put the cursor in the keyword box. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The live custom fields for opportunities (milestone 6.1). Each one
   * becomes a control here, which is `docs/FEATURES.md` §3's "fields appear
   * automatically in Table columns, filters, and the entry form". */
  fields?: CustomField[];
}) {
  const applied = appliedOpportunityFilters(state, fields);
  const [appliedState, setAppliedState] = useState(state);
  const [draft, setDraft] = useState<OpportunityViewState>(state);
  if (state !== appliedState) {
    setAppliedState(state);
    setDraft(state);
  }

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onApply(draft);
    // Applying puts the controls away. Without this the panel stayed open over
    // the board it had just filtered, the chips below it never appeared, and
    // the whole disclosure bought nothing — reported from a screenshot of
    // exactly that (R.1). A popover that stays open after it has been used is
    // not a popover.
    onOpenChange(false);
  }

  function clear() {
    setDraft(emptyOpportunityViewState);
    onApply(emptyOpportunityViewState);
    onOpenChange(false);
  }

  const pinned = pinnedIds(state.ids);
  const customDraft = customFilters(draft.custom, fields);

  /** One custom field's filter, written back into the flat `custom` string. */
  function setCustom(key: string, value: string) {
    const next = new Map(customDraft);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setDraft({ ...draft, custom: customFilterState(next) });
  }

  if (!open) {
    return (
      <div className="filter-summary">
        <button
          type="button"
          className="disclosure-button"
          aria-expanded={false}
          onClick={() => onOpenChange(true)}
        >
          + Filter and sort
        </button>
        {applied.length === 0 ? (
          <span className="meta-row">Showing everything you can see</span>
        ) : (
          <ul className="filter-chips">
            {applied.map((chip) => (
              <li key={chip.key}>
                <button
                  type="button"
                  className="filter-chip"
                  onClick={() => onApply(chip.without)}
                >
                  {chip.label}
                  <span aria-hidden="true">&times;</span>
                  <span className="visually-hidden">, remove this filter</span>
                </button>
              </li>
            ))}
            <li>
              <button
                type="button"
                className="secondary-button"
                onClick={clear}
              >
                Clear all
              </button>
            </li>
          </ul>
        )}
      </div>
    );
  }

  return (
    <form className="filter-bar" onSubmit={apply}>
      <p className="filter-collapse">
        <button
          type="button"
          className="disclosure-button"
          aria-expanded
          onClick={() => onOpenChange(false)}
        >
          Filter and sort
        </button>
      </p>
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
      {/* Value bounds (milestone 6.4). Two inputs rather than a range
          control, because the common case is one side: "over 50k" has no
          upper bound and "under 10k" has no lower. */}
      <label className="filter-field">
        Min value
        <input
          type="number"
          min={0}
          aria-label="Filter by minimum value"
          value={draft.minValue}
          placeholder="Any"
          onChange={(event) =>
            setDraft({ ...draft, minValue: event.target.value })
          }
        />
      </label>
      <label className="filter-field">
        Max value
        <input
          type="number"
          min={0}
          aria-label="Filter by maximum value"
          value={draft.maxValue}
          placeholder="Any"
          onChange={(event) =>
            setDraft({ ...draft, maxValue: event.target.value })
          }
        />
      </label>
      {fields.map((field) => (
        <label className="filter-field" key={field.key}>
          {field.label}
          {field.type === "select" || field.type === "multi_select" ? (
            <select
              aria-label={`Filter by ${field.label}`}
              value={customDraft.get(field.key) ?? ""}
              onChange={(event) => setCustom(field.key, event.target.value)}
            >
              <option value="">{`Any ${field.label.toLowerCase()}`}</option>
              {field.options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          ) : field.type === "checkbox" ? (
            <select
              aria-label={`Filter by ${field.label}`}
              value={customDraft.get(field.key) ?? ""}
              onChange={(event) => setCustom(field.key, event.target.value)}
            >
              <option value="">{`${field.label} or not`}</option>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          ) : (
            // Text, number, date and user all filter as text, matched as a
            // substring like the keyword box: a person filtering a text field
            // is looking for a fragment of it, and a date filters usefully by
            // its year or month prefix because every date here is
            // `YYYY-MM-DD` (`lib/time.ts`).
            <input
              aria-label={`Filter by ${field.label}`}
              value={customDraft.get(field.key) ?? ""}
              onChange={(event) => setCustom(field.key, event.target.value)}
            />
          )}
        </label>
      ))}
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
            className="secondary-button"
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
