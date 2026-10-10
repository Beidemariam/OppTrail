"use client";

import { Link } from "react-router";

import {
  columnsFromState,
  editableField,
  opportunityCell,
  sortFields,
  type Opportunity,
  type CustomField,
  type OpportunityColumn,
  type TableColumn,
  columnLabel,
  customColumnKey,
  type OpportunityEditableKey,
  type OpportunitySortField,
  type OpportunityViewState,
  type Stage,
} from "../lib/domain";
import {
  OpportunityField,
  useOpportunityFieldSave,
  type OpportunityFieldSave,
} from "./InlineEdit";
import { MoveToStage } from "./MoveToStage";
import type { OpportunityViewProps } from "./StageBoard";
import { useOpportunityItem } from "./useOpportunityItem";
import { VirtualList } from "./VirtualList";

// One line per opportunity, unlike the list's two. Measured after mount like
// every other virtualized row, so the compact density does not need a second
// number here.
const ESTIMATED_ROW_HEIGHT = 36;

/**
 * The table view (milestone 2.8): the same filtered, sorted opportunities the
 * board and the list draw, as a spreadsheet grid — one line per deal, columns
 * the reader chooses, and headers that sort.
 *
 * Three things distinguish it from the list, which is otherwise the same data
 * in the same order:
 *
 * - **Columns are a setting**, not a layout (`ColumnPicker`), which is what
 *   `docs/FEATURES.md` §1 calls "the natural home for custom fields" when
 *   those arrive in Phase 6.
 * - **The header sorts.** A header click and the filter bar's sort dropdown
 *   write the same two fields of the view state, so the two controls cannot
 *   disagree and the sort is in the URL either way.
 * - **It is where density is felt** — `docs/DESIGN-SYSTEM.md` introduces
 *   Compact for this view, and one line per row is what makes the difference
 *   visible (`app/Density.tsx`).
 *
 * Not a `<table>`, for the reason the list view is not one either: the rows
 * are windowed, and a `<tbody>` holding only the rows near the viewport is a
 * table that lies about its own shape. Each cell instead carries its column
 * name in visually-hidden text, so a screen reader gets the column context a
 * real table would have given it.
 *
 * **Cells are edited in place** since milestone 2.11, which is what D-087
 * deferred to it: an owner clicks the account, the value or the close date
 * and types over it, with the row and the rows around it still on screen.
 * Stage was already an inline control (`MoveToStage`) and stays one, and the
 * name is not edited here — it is the row's link to its timeline, where its
 * own heading edits it (**D-099**). Every one of them is the same partial
 * `PATCH` the drag and the `[`/`]` chords send (`useEditOpportunity`).
 */
export function OpportunityTable({
  opportunities,
  selectedId,
  focusedId,
  followCursor,
  checkedIds,
  view,
  onFocus,
  onEdit,
  onDelete,
  onMoveToStage,
  onToggleChecked,
  onRangeSelect,
  onSort,
  fields,
}: OpportunityViewProps & {
  view: OpportunityViewState;
  onSort: (field: OpportunitySortField) => void;
  /** The live custom field definitions (milestone 6.1), read once by
   * `DashboardPage` and passed down: they decide which custom columns exist,
   * what each is labelled, and how a value reads. */
  fields: CustomField[];
}) {
  const columns = columnsFromState(view.columns, fields);
  // One per table rather than one per cell: fifty visible cells would
  // otherwise be fifty mutation observers over the same endpoint.
  const saveField = useOpportunityFieldSave();
  // The grid is declared once and shared by the header and every row, so a
  // column cannot be wide in one and narrow in the other.
  const template = `16px minmax(140px, 2fr) ${columns
    .map(() => "minmax(90px, 1fr)")
    .join(" ")} 120px`;

  return (
    <section className="opportunity-table-view" aria-label="Opportunities">
      <div className="table-header" style={{ gridTemplateColumns: template }}>
        <span />
        <SortHeader
          field="name"
          label="Opportunity"
          view={view}
          onSort={onSort}
        />
        {columns.map((column) =>
          // A custom field is not a sort field (milestone 6.1): `sortFields`
          // is a fixed list the filter bar's dropdown shares, and sorting by
          // a JSON value is a comparator per type rather than a column swap.
          // So a custom column is a heading, not a control -- which is also
          // the honest affordance, since clicking it would do nothing.
          customColumnKey(column) !== null ? (
            <span className="table-heading" key={column}>
              {columnLabel(column, fields)}
            </span>
          ) : (
            <SortHeader
              key={column}
              field={column as OpportunitySortField}
              label={columnLabel(column, fields)}
              view={view}
              onSort={onSort}
            />
          ),
        )}
        <span />
      </div>
      <VirtualList
        className="table-rows"
        ariaLabel={`Opportunities as a table, sorted by ${sortLabel(
          view.sortField,
        )}, ${view.sortDirection === "asc" ? "ascending" : "descending"}`}
        items={opportunities}
        estimateItemSize={ESTIMATED_ROW_HEIGHT}
        activeIndex={
          followCursor
            ? opportunities.findIndex(
                (opportunity) => opportunity.id === focusedId,
              )
            : -1
        }
        getItemKey={(opportunity) => opportunity.id}
        renderItem={(opportunity) => (
          <TableRow
            opportunity={opportunity}
            columns={columns}
            fields={fields}
            saveField={saveField}
            template={template}
            selected={selectedId === opportunity.id}
            focused={focusedId === opportunity.id}
            checked={checkedIds.has(opportunity.id)}
            onFocus={onFocus}
            onEdit={onEdit}
            onDelete={onDelete}
            onMoveToStage={onMoveToStage}
            onToggleChecked={onToggleChecked}
            onRangeSelect={onRangeSelect}
          />
        )}
      />
    </section>
  );
}

function sortLabel(field: OpportunitySortField): string {
  return sortFields.find((candidate) => candidate.value === field)!.label;
}

/**
 * One column heading, which is also the control that sorts by it.
 *
 * Its accessible name stays `Sort by <column>` whichever column is active:
 * `aria-sort` is only valid on a real `columnheader`, and folding the
 * direction into the name would rename a control the moment it is used, which
 * breaks both a reader's mental model and every selector aimed at it. Which
 * column the table is ordered by is announced instead on the region holding
 * the rows, where it describes the rows rather than the button.
 */
function SortHeader({
  field,
  label,
  view,
  onSort,
}: {
  field: OpportunitySortField;
  label: string;
  view: OpportunityViewState;
  onSort: (field: OpportunitySortField) => void;
}) {
  const active = view.sortField === field;
  const ascending = view.sortDirection === "asc";
  return (
    <button
      type="button"
      className={`table-sort${active ? " active" : ""}`}
      aria-label={`Sort by ${label}`}
      onClick={() => onSort(field)}
    >
      {label}
      <span aria-hidden="true">{active ? (ascending ? "^" : "v") : ""}</span>
    </button>
  );
}

function TableRow({
  opportunity,
  columns,
  fields,
  saveField,
  template,
  selected,
  focused,
  checked,
  onFocus,
  onEdit,
  onDelete,
  onMoveToStage,
  onToggleChecked,
  onRangeSelect,
}: {
  opportunity: Opportunity;
  columns: TableColumn[];
  fields: CustomField[];
  saveField: OpportunityFieldSave;
  template: string;
  selected: boolean;
  focused: boolean;
  checked: boolean;
  onFocus: (opportunity: Opportunity) => void;
  onEdit: (opportunity: Opportunity) => void;
  onDelete: (opportunity: Opportunity) => void;
  onMoveToStage: (opportunity: Opportunity, stage: Stage) => void;
  onToggleChecked: (opportunity: Opportunity) => void;
  onRangeSelect: (opportunity: Opportunity) => void;
}) {
  const owns = opportunity.current_user_role === "owner";
  const { itemProps, checkboxProps } = useOpportunityItem({
    className: "opportunity-table-row",
    opportunity,
    selected,
    focused,
    checked,
    onFocus,
    onToggleChecked,
    onRangeSelect,
  });

  return (
    <article {...itemProps} style={{ gridTemplateColumns: template }}>
      <input className="card-checkbox" {...checkboxProps} />
      <p className="table-cell table-name">
        <Link to={`/opportunities/${opportunity.id}`}>{opportunity.name}</Link>
        {opportunity.stalled && <span className="stalled-badge">Stalled</span>}
      </p>
      {columns.map((column) => {
        // A custom value is read-only in the grid (milestone 6.1): editing one
        // needs the field's own control -- a select, a checkbox, a date -- and
        // `editableOpportunityFields` declares one editor per built-in field.
        // The record's own form is where a value is set.
        const editable =
          customColumnKey(column) === null &&
          editableField(column as OpportunityColumn);
        return (
          <p className="table-cell" key={column}>
            <span className="visually-hidden">
              {columnLabel(column, fields)}:{" "}
            </span>
            {column === "stage" ? (
              // Already an editor, and a better one than a text box: the
              // stage list is fixed (`AGENTS.md` invariant 6) and this is the
              // same select the board's cards carry.
              owns ? (
                <MoveToStage opportunity={opportunity} onMove={onMoveToStage} />
              ) : (
                opportunity.stage
              )
            ) : editable ? (
              <OpportunityField
                opportunity={opportunity}
                field={column as OpportunityEditableKey}
                editable={owns}
                save={saveField}
              >
                {opportunityCell(opportunity, column, fields)}
              </OpportunityField>
            ) : (
              opportunityCell(opportunity, column, fields)
            )}
          </p>
        );
      })}
      <div className="table-actions">
        {owns && (
          <>
            <button
              type="button"
              className="ghost-button"
              onClick={() => onEdit(opportunity)}
            >
              Edit
            </button>
            <button
              type="button"
              className="ghost-button danger"
              onClick={() => onDelete(opportunity)}
            >
              Delete
            </button>
          </>
        )}
      </div>
    </article>
  );
}
