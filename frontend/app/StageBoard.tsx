"use client";

import { useEffect, useRef, type ChangeEvent, type KeyboardEvent } from "react";
import { Link, useNavigate } from "react-router";

import { stages, type Opportunity } from "../lib/domain";
import { VirtualList } from "./VirtualList";

// Cards vary a little (a wrapped title, a stalled badge) but not by much;
// `VirtualList` measures the real height after mount, so this only has to be
// close enough for the first paint's scrollbar and overscan window.
const ESTIMATED_CARD_HEIGHT = 190;

/**
 * Every opportunity the user can read, in fixed-stage columns
 * (`AGENTS.md` invariant 6). Presentational: the dashboard owns what happens
 * when a card is edited or deleted, and the timeline link is a real URL
 * because an opportunity is addressable from milestone 2.1 onwards.
 *
 * `focusedId` is the keyboard's cursor over the board (milestone 2.4a). The
 * dashboard owns it because `j` and `k` cross stage columns; each column only
 * has to scroll its own card into view when the cursor lands inside it — and
 * only when `followCursor` says the cursor was moved by the keyboard, since
 * a card focused by a click is already where the reader is looking (D-072).
 *
 * `checkedIds` is the bulk-selection set (milestone 2.4c) — separate from
 * both `selectedId` (the opportunity whose timeline is open) and `focusedId`
 * (the keyboard cursor): a card can be all three, or none, independently.
 * The board is the only multi-card surface that exists yet, so it is where
 * the selection model lives; list and table (2.7/2.8) reuse it.
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
  onToggleChecked,
  onRangeSelect,
}: {
  opportunities: Opportunity[];
  selectedId: number | null;
  focusedId: number | null;
  followCursor: boolean;
  checkedIds: ReadonlySet<number>;
  onFocus: (opportunity: Opportunity) => void;
  onEdit: (opportunity: Opportunity) => void;
  onDelete: (opportunity: Opportunity) => void;
  onToggleChecked: (opportunity: Opportunity) => void;
  onRangeSelect: (opportunity: Opportunity) => void;
}) {
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
        return (
          <div className="stage-column" key={stage}>
            <div className="stage-header">
              <h2>{stage}</h2>
              <span>{items.length}</span>
            </div>

            {items.length === 0 ? (
              <p className="empty-state">No opportunities</p>
            ) : (
              <VirtualList
                className="opportunity-list"
                ariaLabel={`${stage} opportunities`}
                items={items}
                estimateItemSize={ESTIMATED_CARD_HEIGHT}
                gap={10}
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
                    onFocus={onFocus}
                    onEdit={onEdit}
                    onDelete={onDelete}
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

function OpportunityCard({
  opportunity,
  selected,
  focused,
  checked,
  onFocus,
  onEdit,
  onDelete,
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
  onToggleChecked: (opportunity: Opportunity) => void;
  onRangeSelect: (opportunity: Opportunity) => void;
}) {
  const cardRef = useRef<HTMLElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const card = cardRef.current;
    // Guarded on `contains`, not on equality: once the reader has tabbed to a
    // control inside the focused card, taking focus back to the card itself
    // would trap them.
    if (focused && card && !card.contains(document.activeElement)) {
      card.focus();
    }
  }, [focused]);

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    // Enter opens the card the cursor is on. Bound here rather than in the
    // document-level map because the card is what has focus, and a global
    // Enter binding would swallow every button press on the page.
    if (event.key === "Enter" && event.target === cardRef.current) {
      event.preventDefault();
      navigate(`/opportunities/${opportunity.id}`);
    }
  }

  const classes = ["opportunity-card"];
  if (selected) {
    classes.push("selected");
  }
  if (focused) {
    classes.push("focused");
  }
  if (checked) {
    classes.push("checked");
  }

  // Shift-click extends the selection from the last-touched card rather
  // than toggling this one (`docs/UX.md`: "checkbox, x, or shift-click
  // range"). Read off `onChange` rather than `onClick` and a `preventDefault`:
  // the checkbox is fully controlled by `checked`, so whichever ids the
  // parent decides belong in the selection are what render checked on the
  // next pass regardless of what the browser's own click toggled first.
  function onCheckboxChange(event: ChangeEvent<HTMLInputElement>) {
    if ((event.nativeEvent as MouseEvent).shiftKey) {
      onRangeSelect(opportunity);
    } else {
      onToggleChecked(opportunity);
    }
  }

  return (
    <article
      className={classes.join(" ")}
      ref={cardRef}
      tabIndex={-1}
      onKeyDown={onKeyDown}
      onFocus={() => onFocus(opportunity)}
    >
      <div>
        <div className="card-title-row">
          <input
            type="checkbox"
            className="card-checkbox"
            aria-label={`Select ${opportunity.name} for bulk actions`}
            checked={checked}
            onChange={onCheckboxChange}
          />
          <h3>{opportunity.name}</h3>
          {opportunity.stalled && (
            <span className="stalled-badge">Stalled</span>
          )}
        </div>
        <p>{opportunity.account_name}</p>
      </div>
      <dl>
        <div>
          <dt>Value</dt>
          <dd>
            {opportunity.currency} {opportunity.value}
          </dd>
        </div>
        <div>
          <dt>Owner</dt>
          <dd>{opportunity.owner_name}</dd>
        </div>
        <div>
          <dt>Your role</dt>
          <dd>{opportunity.current_user_role}</dd>
        </div>
        <div>
          <dt>Close</dt>
          <dd>{opportunity.expected_close_date ?? "Not set"}</dd>
        </div>
      </dl>
      <div className="card-actions">
        <Link
          className="primary-button"
          to={`/opportunities/${opportunity.id}`}
        >
          Timeline
        </Link>
        {opportunity.current_user_role === "owner" && (
          <>
            <button
              type="button"
              className="secondary-button"
              onClick={() => onEdit(opportunity)}
            >
              Edit
            </button>
            <button
              type="button"
              className="danger-button"
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
