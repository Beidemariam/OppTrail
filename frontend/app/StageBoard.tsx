"use client";

import { useState, type DragEvent } from "react";
import { Link, useSearchParams } from "react-router";

import {
  formatMoney,
  stages,
  type Opportunity,
  type Stage,
} from "../lib/domain";
import { opportunityHref } from "../lib/viewState";
import { MoveToStage } from "./MoveToStage";
import { useOpportunityItem } from "./useOpportunityItem";
import { VirtualList } from "./VirtualList";

// Cards vary a little (a wrapped title, a stalled badge) but not by much;
// `VirtualList` measures the real height after mount, so this only has to be
// close enough for the first paint's scrollbar and overscan window.
const ESTIMATED_CARD_HEIGHT = 150;

/** What the board and the list both need from the dashboard: the three
 * selection states, and what to do when an item is acted on. */
export interface OpportunityViewProps {
  opportunities: Opportunity[];
  selectedId: number | null;
  focusedId: number | null;
  followCursor: boolean;
  checkedIds: ReadonlySet<number>;
  onFocus: (opportunity: Opportunity) => void;
  onEdit: (opportunity: Opportunity) => void;
  onDelete: (opportunity: Opportunity) => void;
  onMoveToStage: (opportunity: Opportunity, stage: Stage) => void;
  onToggleChecked: (opportunity: Opportunity) => void;
  onRangeSelect: (opportunity: Opportunity) => void;
}

/**
 * The pipeline board: every opportunity the user can read, in fixed-stage
 * columns (`AGENTS.md` invariant 6), with drag to change stage (milestone
 * 2.7).
 *
 * **A drag is the same write as every other stage change.** It calls
 * `onMoveToStage`, which is what the card's move-to-stage select and the
 * `[`/`]` chords call too — one path to `PATCH`, so the system timeline entry
 * the server writes cannot depend on how the reader asked. Only the owner may
 * change an opportunity's fields, so only their cards are draggable and only
 * their cards carry the select; a column still accepts a drop from any card
 * it is offered, because the drag could not have started otherwise.
 *
 * `focusedId` is the keyboard's cursor (milestone 2.4a). The dashboard owns it
 * because `j` and `k` cross stage columns; each column only has to scroll its
 * own card into view when the cursor lands inside it — and only when
 * `followCursor` says the cursor was moved by the keyboard, since a card
 * focused by a click is already where the reader is looking (D-072).
 *
 * `checkedIds` is the bulk-selection set (milestone 2.4c) — separate from
 * both `selectedId` (the opportunity whose timeline is open) and `focusedId`:
 * a card can be all three, or none, independently.
 */
export function StageBoard({
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
  // The drag in progress, held here rather than read back off `dataTransfer`:
  // `dragover` is not allowed to read the payload (only `drop` is), and the
  // column needs to know whose drag this is to refuse its own cards.
  const [dragging, setDragging] = useState<Opportunity | null>(null);
  const [dragOverStage, setDragOverStage] = useState<string | null>(null);

  function onDrop(stage: Stage) {
    const moved = dragging;
    setDragging(null);
    setDragOverStage(null);
    if (moved && moved.stage !== stage) {
      onMoveToStage(moved, stage);
    }
  }

  return (
    /* The board scrolls horizontally, so it needs to be focusable or a
       keyboard-only user cannot reach the stages past the fold
       (axe: scrollable-region-focusable). */
    <section
      className="stage-board"
      aria-label="Opportunities grouped by stage"
      tabIndex={0}
    >
      {stages.map((stage) => {
        const items = opportunities.filter(
          (opportunity) => opportunity.stage === stage,
        );
        const value = items.reduce(
          (total, opportunity) => total + Number(opportunity.value),
          0,
        );
        return (
          <div
            className={`stage-column${dragOverStage === stage ? " drop-target" : ""}`}
            key={stage}
            onDragOver={(event: DragEvent<HTMLDivElement>) => {
              if (!dragging) {
                return;
              }
              // Without this the browser refuses the drop, which is what makes
              // a drag target a drop target.
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
              setDragOverStage(stage);
            }}
            onDragLeave={(event: DragEvent<HTMLDivElement>) => {
              // Leaving for a child of this column is not leaving the column.
              if (!event.currentTarget.contains(event.relatedTarget as Node)) {
                setDragOverStage((current) =>
                  current === stage ? null : current,
                );
              }
            }}
            onDrop={(event: DragEvent<HTMLDivElement>) => {
              event.preventDefault();
              onDrop(stage);
            }}
          >
            <div className="stage-header">
              <h2>{stage}</h2>
              <span className="stage-count">{items.length}</span>
              <p className="stage-total">{formatTotal(items, value)}</p>
            </div>

            {items.length === 0 ? (
              <p className="empty-state">
                {dragging ? "Drop here to move" : "Nothing in this stage"}
              </p>
            ) : (
              <VirtualList
                className="opportunity-list"
                ariaLabel={`${stage} opportunities`}
                items={items}
                estimateItemSize={ESTIMATED_CARD_HEIGHT}
                gap={8}
                activeIndex={
                  followCursor
                    ? items.findIndex(
                        (opportunity) => opportunity.id === focusedId,
                      )
                    : -1
                }
                getItemKey={(opportunity) => opportunity.id}
                renderItem={(opportunity) => (
                  <OpportunityCard
                    opportunity={opportunity}
                    selected={selectedId === opportunity.id}
                    focused={focusedId === opportunity.id}
                    checked={checkedIds.has(opportunity.id)}
                    dragging={dragging?.id === opportunity.id}
                    onDragStart={setDragging}
                    onDragEnd={() => {
                      setDragging(null);
                      setDragOverStage(null);
                    }}
                    onFocus={onFocus}
                    onEdit={onEdit}
                    onDelete={onDelete}
                    onMoveToStage={onMoveToStage}
                    onToggleChecked={onToggleChecked}
                    onRangeSelect={onRangeSelect}
                  />
                )}
              />
            )}
          </div>
        );
      })}
    </section>
  );
}

/** A column's weight, which is what a pipeline board is read for. The
 * currency is the first card's: this app has no conversion, so a column of
 * mixed currencies reports the count alone rather than adding them up. */
function formatTotal(items: Opportunity[], value: number): string {
  if (items.length === 0) {
    return "";
  }
  const currency = items[0].currency;
  if (items.some((opportunity) => opportunity.currency !== currency)) {
    return `${items.length} in mixed currencies`;
  }
  return formatMoney(currency, value);
}

function OpportunityCard({
  opportunity,
  selected,
  focused,
  checked,
  dragging,
  onDragStart,
  onDragEnd,
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
  dragging: boolean;
  onDragStart: (opportunity: Opportunity) => void;
  onDragEnd: () => void;
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
    className: `opportunity-card${dragging ? " dragging" : ""}`,
    opportunity,
    selected,
    focused,
    checked,
    onFocus,
    onToggleChecked,
    onRangeSelect,
  });

  return (
    <article
      {...itemProps}
      draggable={owns}
      onDragStart={(event: DragEvent<HTMLElement>) => {
        // Firefox starts no drag at all without a payload, even one nothing
        // reads back: the move itself is carried in React state, because a
        // `dragover` handler is not allowed to look inside `dataTransfer`.
        event.dataTransfer.setData("text/plain", String(opportunity.id));
        event.dataTransfer.effectAllowed = "move";
        onDragStart(opportunity);
      }}
      onDragEnd={onDragEnd}
    >
      <div className="card-title-row">
        <input className="card-checkbox" {...checkboxProps} />
        <h3>
          {/* Not natively draggable: an anchor drags its own URL, which would
              start a drag the board is not part of. */}
          <Link draggable={false} to={opportunityHref(opportunity.id, params)}>
            {opportunity.name}
          </Link>
        </h3>
        {opportunity.stalled && <span className="stalled-badge">Stalled</span>}
      </div>
      <p className="card-account">{opportunity.account_name}</p>
      <p className="card-value">
        {formatMoney(opportunity.currency, opportunity.value)}
      </p>
      <p className="card-meta">
        <span>
          {opportunity.owner_name}
          {owns ? "" : ` (you are a ${opportunity.current_user_role})`}
        </span>
        <span aria-hidden="true">·</span>
        <span>
          {opportunity.expected_close_date
            ? `Closes ${opportunity.expected_close_date}`
            : "No close date"}
        </span>
      </p>
      {owns && (
        <div className="card-actions">
          <MoveToStage opportunity={opportunity} onMove={onMoveToStage} />
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
        </div>
      )}
    </article>
  );
}
