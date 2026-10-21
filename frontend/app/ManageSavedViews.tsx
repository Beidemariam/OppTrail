"use client";

import { FormEvent, useState } from "react";

import {
  savedViewEntityLabel,
  savedViewVisibility,
  type SavedView,
  type SavedViewEntity,
} from "../lib/domain";
import { useDeleteSavedView, useUpdateSavedView } from "../lib/queries";
import { Modal } from "./Modal";
import { SavedViewFields, type SavedViewDraft } from "./SavedViewFields";

/**
 * Rename a view, change who can use it, point it at the filters on screen, or
 * delete it (milestone 2.13, **D-082**).
 *
 * This dialog exists so the view list does not have to carry the controls.
 * The list used to render a `Delete "<name>"` button beside every view the
 * caller owned, which put a permanent destructive control on the dashboard
 * for an action taken once in a while -- `AGENTS.md`'s Design bar now rules
 * that out in general, and this is the affordance it asks for instead.
 *
 * Only the caller's own views appear: a shared view is applied by everyone
 * and edited by its creator (`docs/FEATURES.md` §1), which is also exactly
 * what `routes_saved_views.py` enforces, so offering the control to anyone
 * else would be offering an action the API refuses.
 *
 * Deleting still asks -- a view has no restore route, so this is the
 * `docs/UX.md` case that confirms rather than offering Undo (D-069) -- but it
 * asks in the row instead of through `app/ConfirmDialog.tsx`, because that is
 * a second modal layer and two focus traps over one page fight for focus
 * rather than stacking.
 */
export function ManageSavedViews<T extends Record<string, string>>({
  entity,
  views,
  userId,
  state,
  onClose,
}: {
  entity: SavedViewEntity;
  views: SavedView[];
  userId: number | undefined;
  /** The filters currently on screen, which an edit can adopt. */
  state: T;
  onClose: () => void;
}) {
  const entityLabel = savedViewEntityLabel(entity);
  const updateView = useUpdateSavedView(entity);
  const deleteView = useDeleteSavedView(entity);
  const [editingId, setEditingId] = useState<number | null>(null);
  // Deleting confirms in the row rather than through `useConfirm`: this is
  // already inside a dialog, and `app/ConfirmDialog.tsx` is another modal
  // layer with its own focus trap -- two of them over one page fight over
  // focus rather than stacking. The question is the same question, asked
  // where the answer is.
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<SavedViewDraft | null>(null);
  const [adoptFilters, setAdoptFilters] = useState(false);

  const mine = views.filter((view) => view.created_by === userId);

  function startEditing(view: SavedView) {
    setEditingId(view.id);
    setConfirmingId(null);
    setAdoptFilters(false);
    setDraft({
      name: view.name,
      isShared: view.is_shared,
      isDefault: view.is_default,
    });
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (editingId === null || !draft || !draft.name.trim()) {
      return;
    }
    updateView.mutate(
      {
        id: editingId,
        name: draft.name.trim(),
        is_shared: draft.isShared,
        is_default: draft.isDefault,
        ...(adoptFilters ? { filters: state } : {}),
      },
      { onSuccess: () => setEditingId(null) },
    );
  }

  return (
    <Modal
      label={`Manage ${entityLabel} views`}
      title={`Manage ${entityLabel} views`}
      onClose={onClose}
    >
      {mine.length === 0 ? (
        <p className="field-hint">
          You have not saved a {entityLabel} view yet. Filter the{" "}
          {entityLabel === "opportunity" ? "board" : "timeline"} the way you
          want it, then save it under a name.
        </p>
      ) : (
        <ul className="manage-views">
          {mine.map((view) => (
            <li key={view.id}>
              {editingId === view.id && draft ? (
                <form className="stacked-form" onSubmit={save}>
                  <SavedViewFields draft={draft} onChange={setDraft} />
                  <label className="choice">
                    <input
                      type="checkbox"
                      checked={adoptFilters}
                      onChange={(event) =>
                        setAdoptFilters(event.target.checked)
                      }
                    />
                    Replace its filters with the ones on screen now
                  </label>
                  <div className="row-actions">
                    <button className="primary-button" type="submit">
                      Save changes
                    </button>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => setEditingId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <div className="manage-view-row">
                  <span className="manage-view-name">{view.name}</span>
                  <span className="view-badge">
                    {savedViewVisibility(view, userId)}
                  </span>
                  {view.is_default && (
                    <span className="view-badge">default</span>
                  )}
                  {confirmingId === view.id ? (
                    <>
                      <span className="field-hint">
                        {view.is_shared
                          ? "Delete it for everyone? No opportunity is affected, and the same filters can be saved again."
                          : "Delete it? No opportunity is affected, and the same filters can be saved again."}
                      </span>
                      <button
                        type="button"
                        className="danger-button"
                        autoFocus
                        onClick={() => {
                          setConfirmingId(null);
                          deleteView.mutate(view.id);
                        }}
                      >
                        Delete view
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => setConfirmingId(null)}
                      >
                        Keep it
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="secondary-button"
                        aria-label={`Edit view ${view.name}`}
                        onClick={() => startEditing(view)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        aria-label={`Delete view ${view.name}`}
                        onClick={() => setConfirmingId(view.id)}
                      >
                        Delete
                      </button>
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {updateView.isError && (
        <p className="error">{updateView.error.message}</p>
      )}
      {deleteView.isError && (
        <p className="error">{deleteView.error.message}</p>
      )}
    </Modal>
  );
}
