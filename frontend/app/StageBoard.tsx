"use client";

import { Link } from "react-router";

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
 */
export function StageBoard({
  opportunities,
  selectedId,
  onEdit,
  onDelete,
}: {
  opportunities: Opportunity[];
  selectedId: number | null;
  onEdit: (opportunity: Opportunity) => void;
  onDelete: (opportunity: Opportunity) => void;
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
                getItemKey={(opportunity) => opportunity.id}
                renderItem={(opportunity) => (
                  <article
                    className={
                      selectedId === opportunity.id
                        ? "opportunity-card selected"
                        : "opportunity-card"
                    }
                  >
                    <div>
                      <div className="card-title-row">
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
                )}
              />
            )}
          </div>
        );
      })}
    </section>
  );
}
