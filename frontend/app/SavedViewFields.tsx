"use client";

import { useId } from "react";

/** The three things a reader decides about a saved view, in both the dialog
 * that creates one and the row that edits one. */
export interface SavedViewDraft {
  name: string;
  isShared: boolean;
  isDefault: boolean;
}

export const emptySavedViewDraft: SavedViewDraft = {
  name: "",
  isShared: false,
  isDefault: false,
};

/**
 * Name, who can use it, and whether it opens by default (milestone 2.13).
 *
 * The visibility choice is deliberate rather than a checkbox that defaults to
 * off: **D-076** ruled that the author picks between "just for me" and
 * "everyone" at the moment of saving, in the pattern the product owner named,
 * because the failure it replaces was a reviewer who could not tell the two
 * kinds of view apart at all.
 *
 * The sentence under the choice is the part that earns its place. Sharing a
 * view publishes its *name* to every signed-in user while its results stay
 * permission-filtered per reader, so "Acme renewal push" is a small
 * disclosure and a colleague opening the view can legitimately see fewer rows
 * than its author. Saying both here is what stops either from being a
 * surprise later.
 */
export function SavedViewFields({
  draft,
  onChange,
}: {
  draft: SavedViewDraft;
  onChange: (draft: SavedViewDraft) => void;
}) {
  // Both dialogs can be open over the same page, and the manage dialog edits
  // one row at a time, so the radio group is named per instance rather than
  // globally.
  const group = useId();

  return (
    <>
      <label className="stacked-field">
        View name
        <input
          name="name"
          value={draft.name}
          autoFocus
          onChange={(event) => onChange({ ...draft, name: event.target.value })}
        />
      </label>

      <fieldset className="choice-group">
        <legend>Who can use this view</legend>
        <label className="choice">
          <input
            type="radio"
            name={group}
            checked={!draft.isShared}
            onChange={() => onChange({ ...draft, isShared: false })}
          />
          Just for me
        </label>
        <label className="choice">
          <input
            type="radio"
            name={group}
            checked={draft.isShared}
            onChange={() => onChange({ ...draft, isShared: true })}
          />
          Everyone
        </label>
        <p className="field-hint">
          Everyone signed in can apply a shared view and sees the name you give
          it. They still only see the opportunities shared with them, so a
          shared view can show a colleague fewer rows than it shows you.
        </p>
      </fieldset>

      <label className="choice">
        <input
          type="checkbox"
          checked={draft.isDefault}
          onChange={(event) =>
            onChange({ ...draft, isDefault: event.target.checked })
          }
        />
        Open this view by default
      </label>
    </>
  );
}
