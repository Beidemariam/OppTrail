"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import type { SavedViewEntity } from "../lib/domain";
import {
  useCreateSavedView,
  useDeleteSavedView,
  useSavedViews,
  useSession,
} from "../lib/queries";

/**
 * Apply, save and delete a named filter/sort set for one entity's URL state
 * (milestone 2.2, `docs/FEATURES.md` §1).
 *
 * Generic over the state shape (`TimelineFilters` or `OpportunityViewState`,
 * both `Record<string, string>` — `lib/viewState.ts`) so the same component
 * serves the timeline's filter bar and the opportunity board without a second
 * implementation of "apply a saved set of query parameters".
 */
export function SavedViewsMenu<T extends Record<string, string>>({
  entity,
  state,
  defaults,
  onApply,
}: {
  entity: SavedViewEntity;
  state: T;
  defaults: T;
  onApply: (state: T) => void;
}) {
  const session = useSession();
  const views = useSavedViews(entity);
  const createView = useCreateSavedView();
  const deleteView = useDeleteSavedView(entity);
  const [saving, setSaving] = useState(false);

  // Loads the caller's default view exactly once, and only when the page
  // opened with no filter already in the URL — a deep link or a saved view
  // just applied should never be overridden by a different default arriving
  // later from a slower request. The effect runs once per mount because it
  // only reacts to the views finishing their first load, not to `state`
  // itself, which `onApply` goes on to change.
  const appliedDefault = useRef(false);
  const atDefaults = Object.keys(defaults).every(
    (key) => state[key] === defaults[key],
  );
  useEffect(() => {
    if (appliedDefault.current || !atDefaults || !views.data) {
      return;
    }
    appliedDefault.current = true;
    const defaultView = views.data.find((view) => view.is_default);
    if (defaultView) {
      onApply({ ...defaults, ...(defaultView.filters as Partial<T>) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [views.data]);

  // Both the board and an open timeline render one of these at once, so every
  // label spells out which entity it applies to — otherwise a query by label
  // text (or by this app's own tests) could not tell the two apart.
  const entityLabel = entity === "opportunities" ? "opportunity" : "timeline";

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const name = String(data.get("name") ?? "").trim();
    if (!name) {
      return;
    }
    createView.mutate(
      {
        name,
        entity,
        filters: state,
        sort: {},
        group_by: entity === "opportunities" ? "stage" : null,
        is_shared: data.get("is_shared") === "on",
        is_default: data.get("is_default") === "on",
      },
      { onSuccess: () => setSaving(false) },
    );
  }

  return (
    <div className="saved-views">
      <label htmlFor={`saved-view-select-${entity}`}>
        Saved {entityLabel} views
      </label>
      <select
        id={`saved-view-select-${entity}`}
        value=""
        onChange={(event) => {
          const view = views.data?.find(
            (candidate) => String(candidate.id) === event.target.value,
          );
          if (view) {
            onApply({ ...defaults, ...(view.filters as Partial<T>) });
          }
        }}
      >
        <option value="">Apply a saved view...</option>
        {(views.data ?? []).map((view) => (
          <option key={view.id} value={view.id}>
            {view.name}
            {view.is_default ? " (default)" : ""}
          </option>
        ))}
      </select>

      {(views.data ?? [])
        .filter((view) => view.created_by === session.data?.id)
        .map((view) => (
          <button
            key={view.id}
            type="button"
            className="secondary-button compact-button"
            aria-label={`Delete saved view ${view.name}`}
            onClick={() => deleteView.mutate(view.id)}
          >
            Delete &ldquo;{view.name}&rdquo;
          </button>
        ))}

      {saving ? (
        <form className="form saved-view-form" onSubmit={save}>
          <input
            name="name"
            placeholder="View name"
            aria-label={`Saved ${entityLabel} view name`}
          />
          <label>
            <input type="checkbox" name="is_shared" /> Shared
          </label>
          <label>
            <input type="checkbox" name="is_default" /> Default
          </label>
          <button className="primary-button" type="submit">
            Save {entityLabel} view
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setSaving(false)}
          >
            Cancel
          </button>
        </form>
      ) : (
        <button
          type="button"
          className="secondary-button compact-button"
          onClick={() => setSaving(true)}
        >
          Save current {entityLabel} view
        </button>
      )}

      {createView.isError && (
        <p className="error">{createView.error.message}</p>
      )}
      {deleteView.isError && (
        <p className="error">{deleteView.error.message}</p>
      )}
    </div>
  );
}
