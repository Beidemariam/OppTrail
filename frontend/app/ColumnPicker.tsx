"use client";

import { useId, useState } from "react";

import {
  columnsFromState,
  opportunityColumns,
  type OpportunityColumn,
} from "../lib/domain";

/**
 * Which columns the table draws (milestone 2.8) — `ColumnPicker` from
 * `docs/DESIGN-SYSTEM.md`'s domain inventory.
 *
 * The choice is part of the URL-serialized view state, so a table with a
 * particular set of columns is linkable and is what a saved view stores
 * beside its filters (`lib/viewState.ts`, and `filters` is opaque JSON so no
 * migration is needed for it — D-062).
 *
 * A disclosure rather than a popover: this app has no `Popover` primitive yet
 * and a checkbox list does not need one (D-073 — each Radix primitive arrives
 * with the milestone that has a caller for it). The panel is plain markup
 * under a button that says how many columns are on, which is the fact a
 * reader wants before opening it.
 */
export function ColumnPicker({
  columns,
  onChange,
}: {
  /** The comma-separated column string from the view state. */
  columns: string;
  onChange: (columns: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const chosen = columnsFromState(columns);

  function toggle(column: OpportunityColumn) {
    const next = chosen.includes(column)
      ? chosen.filter((candidate) => candidate !== column)
      : // Kept in the declared order rather than in the order they were
        // ticked, so the table's columns read the same way for everyone.
        opportunityColumns
          .map((candidate) => candidate.key)
          .filter(
            (candidate) => chosen.includes(candidate) || candidate === column,
          );
    onChange(next.join(","));
  }

  return (
    <div className="column-picker">
      <button
        type="button"
        className="secondary-button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
      >
        Columns ({chosen.length})
      </button>
      {open && (
        <fieldset className="column-picker-panel" id={panelId}>
          <legend>Columns shown in the table</legend>
          {opportunityColumns.map((column) => {
            const checked = chosen.includes(column.key);
            return (
              <label key={column.key}>
                <input
                  type="checkbox"
                  checked={checked}
                  // The last column standing cannot be turned off: a table of
                  // names alone is the list view, reached from the switcher.
                  disabled={checked && chosen.length === 1}
                  onChange={() => toggle(column.key)}
                />
                {column.label}
              </label>
            );
          })}
        </fieldset>
      )}
    </div>
  );
}
