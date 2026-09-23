"use client";

import { Link } from "react-router";

import {
  columnsFromState,
  opportunityCell,
  opportunityColumns,
  sortFields,
  type Opportunity,
  type OpportunityColumn,
  type OpportunitySortField,
  type OpportunityViewState,
  type Stage,
} from "../lib/domain";
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
 * Inline cell editing is **not** here: milestone 2.11 owns editing content
 * where it is read, for entries, notes and opportunity fields together, and
 * writing it twice is how the two drift (D-087).
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
}: OpportunityViewProps & {
  view: OpportunityViewState;
  onSort: (field: OpportunitySortField) => void;
}) {
  const columns = columnsFromState(view.columns);
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
        {columns.map((column) => (
          <SortHeader
            key={column}
            field={column}
            label={columnLabel(column)}
            view={view}
            onSort={onSort}
          />
        ))}
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

function columnLabel(column: OpportunityColumn): string {
  return opportunityColumns.find((candidate) => candidate.key === column)!
    .label;
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
  columns: OpportunityColumn[];
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
      {columns.map((column) =>
        column === "stage" ? (
          <p className="table-cell" key={column}>
            <span className="visually-hidden">Stage: </span>
            {owns ? (
              <MoveToStage opportunity={opportunity} onMove={onMoveToStage} />
            ) : (
              opportunity.stage
            )}
          </p>
        ) : (
          <p className="table-cell" key={column}>
            <span className="visually-hidden">{columnLabel(column)}: </span>
            {opportunityCell(opportunity, column)}
          </p>
        ),
      )}
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
