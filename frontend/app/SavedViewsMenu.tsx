"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import {
  matchesSavedView,
  savedViewEntityLabel,
  savedViewLabel,
  savedViewVisibility,
  type SavedViewEntity,
} from "../lib/domain";
import { useCreateSavedView, useSavedViews, useSession } from "../lib/queries";
import { ManageSavedViews } from "./ManageSavedViews";
import { Modal } from "./Modal";
import {
  SavedViewFields,
  emptySavedViewDraft,
  type SavedViewDraft,
} from "./SavedViewFields";

/**
 * Apply, save and manage a named filter/sort set for one entity's URL state
 * (milestone 2.2, `docs/FEATURES.md` §1; reworked in 2.13).
 *
 * Generic over the state shape (`TimelineFilters` or `OpportunityViewState`,
 * both `Record<string, string>` -- `lib/viewState.ts`) so the same component
 * serves the timeline's filter bar and the opportunity board without a second
 * implementation of "apply a saved set of query parameters".
 *
 * Three things changed in 2.13, all from **D-076** and **D-082**:
 *
 * - **Saving says who the view is for**, in a dialog, rather than offering an
 *   unexplained `Shared` checkbox beside the name.
 * - **The strip says which view is applied and what kind it is**, so a view
 *   that reached the reader from a colleague is not mistaken for their own.
 *   Nothing records which view is applied -- applying one only writes its
 *   filters into the URL -- so it is recognised by comparing
 *   (`matchesSavedView`), which also means the line disappears the moment a
 *   filter is changed.
 * - **Editing and deleting moved behind Manage**, off the always-visible list.
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
  const [saving, setSaving] = useState(false);
  const [managing, setManaging] = useState(false);
  const [draft, setDraft] = useState<SavedViewDraft>(emptySavedViewDraft);

  // Loads the caller's default view exactly once, and only when the page
  // opened with no filter already in the URL -- a deep link or a saved view
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
  // label spells out which entity it applies to -- otherwise a query by label
  // text (or by this app's own tests) could not tell the two apart.
  const entityLabel = savedViewEntityLabel(entity);
  const userId = session.data?.id;
  const available = views.data ?? [];
  // Which view the filters on screen amount to, if any. Not tracked state:
  // see the note above.
  const applied = available.find((view) =>
    matchesSavedView(view, state, defaults),
  );

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = draft.name.trim();
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
        is_shared: draft.isShared,
        is_default: draft.isDefault,
      },
      { onSuccess: closeSave },
    );
  }

  /** Closing empties the form: the next view saved is a new decision, not a
   * half-finished one from last time. */
  function closeSave() {
    setSaving(false);
    setDraft(emptySavedViewDraft);
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
          const view = available.find(
            (candidate) => String(candidate.id) === event.target.value,
          );
          if (view) {
            onApply({ ...defaults, ...(view.filters as Partial<T>) });
          }
        }}
      >
        <option value="">Apply a saved view...</option>
        {available.map((view) => (
          <option key={view.id} value={view.id}>
            {savedViewLabel(view, userId)}
          </option>
        ))}
      </select>

      <button
        type="button"
        className="secondary-button"
        onClick={() => setSaving(true)}
      >
        Save current {entityLabel} view
      </button>
      <button
        type="button"
        className="secondary-button"
        onClick={() => setManaging(true)}
      >
        Manage {entityLabel} views
      </button>

      {applied && (
        <p className="applied-view">
          Showing <strong>{applied.name}</strong>
          <span className="view-badge">
            {savedViewVisibility(applied, userId)}
          </span>
        </p>
      )}
      {applied && applied.created_by !== userId && (
        <p className="field-hint">
          {applied.creator_name} shared the filters, not the opportunities. You
          see only the ones shared with you, so this view can look different to
          you than it does to them.
        </p>
      )}

      {saving && (
        <Modal
          label={`Save ${entityLabel} view`}
          title={`Save ${entityLabel} view`}
          onClose={closeSave}
        >
          <form className="stacked-form" onSubmit={save}>
            <SavedViewFields draft={draft} onChange={setDraft} />
            <div className="row-actions">
              <button className="primary-button" type="submit">
                Save view
              </button>
              <button
                className="secondary-button"
                type="button"
                onClick={closeSave}
              >
                Cancel
              </button>
            </div>
            {createView.isError && (
              <p className="error">{createView.error.message}</p>
            )}
          </form>
        </Modal>
      )}

      {managing && (
        <ManageSavedViews
          entity={entity}
          views={available}
          userId={userId}
          state={state}
          onClose={() => setManaging(false)}
        />
      )}
    </div>
  );
}
