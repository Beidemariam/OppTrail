"use client";

import { Link, useSearchParams } from "react-router";

import { formatMoney, type Opportunity, type Stage } from "../lib/domain";
import { opportunityHref } from "../lib/viewState";
import { MoveToStage } from "./MoveToStage";
import type { OpportunityViewProps } from "./StageBoard";
import { useOpportunityItem } from "./useOpportunityItem";
import { VirtualList } from "./VirtualList";

// One dense row (`docs/DESIGN-SYSTEM.md`: comfortable density, 40px rows),
// measured after mount like every other virtualized row.
const ESTIMATED_ROW_HEIGHT = 44;

/**
 * The list view (milestone 2.7): the same filtered, sorted opportunities the
 * board draws, laid out as dense rows in the sort order rather than regrouped
 * into stage columns.
 *
 * It is a different renderer, not a different query — `DashboardPage` filters
 * and sorts once and hands the result to whichever view the URL asked for, so
 * switching views costs no request and keeps the selection, the cursor and
 * the filters exactly where they were.
 *
 * Stage is a control here rather than a column position: with no column to
 * drop into, `MoveToStage` is how an owner moves an opportunity on
 * (`app/MoveToStage.tsx`).
 *
 * It is never asked to draw nothing: `DashboardPage` answers an empty list
 * itself, and its two answers differ — "there are none yet" and "your filters
 * removed them all" need different next actions (`docs/DESIGN-SYSTEM.md`).
 */
export function OpportunityList({
  opportunities,
  selectedId,
  focusedId,
  followCursor,
  checkedIds,
  onFocus,
  onEdit,
  onDelete,
  onMoveToStage,
  onToggleChecked,
  onRangeSelect,
}: OpportunityViewProps) {
  return (
    <section className="opportunity-list-view" aria-label="Opportunities">
      {/* A header row rather than a table: the rows are virtualized, and a
          windowed `<tbody>` is a table whose rows lie about their position.
          The labels are `aria-hidden` because each cell names itself. */}
      <div className="list-header" aria-hidden="true">
        <span />
        <span>Opportunity</span>
        <span>Stage</span>
        <span>Value</span>
        <span>Close</span>
        <span>Owner</span>
        <span />
      </div>
      <VirtualList
        className="opportunity-rows"
        ariaLabel="Opportunities, most recent activity first"
        items={opportunities}
        estimateItemSize={ESTIMATED_ROW_HEIGHT}
        gap={4}
        activeIndex={
          followCursor
            ? opportunities.findIndex(
                (opportunity) => opportunity.id === focusedId,
              )
            : -1
        }
        getItemKey={(opportunity) => opportunity.id}
        renderItem={(opportunity) => (
          <OpportunityRow
            opportunity={opportunity}
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

function OpportunityRow({
  opportunity,
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
  // The board's view state travels with the link (R.1): a deal is its own
  // page now, so the way back has to be able to restore the list.
  const [params] = useSearchParams();
  const owns = opportunity.current_user_role === "owner";
  const { itemProps, checkboxProps } = useOpportunityItem({
    className: "opportunity-row",
    opportunity,
    selected,
    focused,
    checked,
    onFocus,
    onToggleChecked,
    onRangeSelect,
  });

  return (
    <article {...itemProps}>
      <input className="card-checkbox" {...checkboxProps} />
      <div className="row-name">
        <h3>
          <Link to={opportunityHref(opportunity.id, params)}>
            {opportunity.name}
          </Link>
        </h3>
        <p>{opportunity.account_name}</p>
      </div>
      <div className="row-stage">
        {owns ? (
          <MoveToStage opportunity={opportunity} onMove={onMoveToStage} />
        ) : (
          <span className="stage-chip">{opportunity.stage}</span>
        )}
      </div>
      <p className="row-value">
        {formatMoney(opportunity.currency, opportunity.value)}
      </p>
      <p className="row-close">
        {opportunity.expected_close_date ?? "Not set"}
        {opportunity.stalled && <span className="stalled-badge">Stalled</span>}
      </p>
      <p className="row-owner">
        {opportunity.owner_name}
        {owns ? "" : ` (${opportunity.current_user_role})`}
      </p>
      <div className="row-actions">
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
