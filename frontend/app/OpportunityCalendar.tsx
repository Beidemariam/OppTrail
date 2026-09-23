"use client";

import { Link } from "react-router";

import {
  calendarWeeks,
  closingOn,
  formatMoney,
  monthLabel,
  shiftMonth,
  weekdayLabels,
  withoutCloseDate,
  type Opportunity,
} from "../lib/domain";
import type { OpportunityViewProps } from "./StageBoard";
import { useOpportunityItem } from "./useOpportunityItem";

/**
 * The calendar view (milestone 2.8): the same filtered opportunities, placed
 * on the month their deal is expected to close.
 *
 * `docs/FEATURES.md` §1 describes it as "expected close dates and follow-up
 * dates". Only the first half is here, because the second has no
 * cross-opportunity read to draw from — a follow-up date lives on a timeline
 * entry, and nothing returns entries across opportunities. Phase 4 builds
 * exactly that (milestone 4.1's "My Tasks across opportunities", 4.2's
 * migration of `timeline_entries.follow_up_date` into tasks), so the second
 * layer arrives with the query that can feed it rather than with a bespoke
 * endpoint built here and replaced there (**D-088**).
 *
 * Not virtualized, and deliberately: a month is at most six week rows, and
 * what varies is how many deals sit in one day's cell. `VirtualList` windows
 * a long scrolling column; a calendar grid is neither.
 *
 * Deals with no close date are listed under the grid rather than dropped. A
 * view that silently omits rows is how a reader concludes they have fewer
 * deals than they do — the same failure D-076 found in the empty states.
 */
export function OpportunityCalendar({
  opportunities,
  selectedId,
  focusedId,
  checkedIds,
  month,
  today,
  onFocus,
  onToggleChecked,
  onRangeSelect,
  onMonthChange,
}: Pick<
  OpportunityViewProps,
  | "opportunities"
  | "selectedId"
  | "focusedId"
  | "checkedIds"
  | "onFocus"
  | "onToggleChecked"
  | "onRangeSelect"
> & {
  /** The month on screen, `YYYY-MM`, already resolved by the dashboard. */
  month: string;
  /** Today as `YYYY-MM-DD`, so the cell for it can be marked. Passed in
   * rather than read here, because a component that reads the clock cannot be
   * tested without one. */
  today: string;
  onMonthChange: (month: string) => void;
}) {
  const weeks = calendarWeeks(month);
  const undated = withoutCloseDate(opportunities);

  return (
    <section className="calendar-view" aria-label="Opportunities by close date">
      <div className="calendar-toolbar">
        <button
          type="button"
          className="secondary-button"
          onClick={() => onMonthChange(shiftMonth(month, -1))}
        >
          Previous month
        </button>
        {/* The heading is the live region as well: the month changes under
            the same two buttons, so a reader who cannot see the grid still
            hears which month they landed on. */}
        <h2 aria-live="polite">{monthLabel(month)}</h2>
        <button
          type="button"
          className="secondary-button"
          onClick={() => onMonthChange(shiftMonth(month, 1))}
        >
          Next month
        </button>
        <button
          type="button"
          className="ghost-button"
          onClick={() => onMonthChange("")}
        >
          Today
        </button>
      </div>

      <div className="calendar-grid">
        <div className="calendar-weekdays" aria-hidden="true">
          {weekdayLabels.map((day) => (
            <span key={day}>{day}</span>
          ))}
        </div>
        {weeks.map((week) => (
          <div className="calendar-week" key={week[0]}>
            {week.map((day) => {
              const closing = closingOn(opportunities, day);
              return (
                <div
                  className={[
                    "calendar-day",
                    day.startsWith(`${month}-`) ? "" : "adjacent",
                    day === today ? "today" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  key={day}
                >
                  <p className="calendar-date">
                    <span className="visually-hidden">{day}</span>
                    <span aria-hidden="true">{Number(day.slice(8))}</span>
                  </p>
                  {closing.map((opportunity) => (
                    <CalendarChip
                      key={opportunity.id}
                      opportunity={opportunity}
                      selected={selectedId === opportunity.id}
                      focused={focusedId === opportunity.id}
                      checked={checkedIds.has(opportunity.id)}
                      onFocus={onFocus}
                      onToggleChecked={onToggleChecked}
                      onRangeSelect={onRangeSelect}
                    />
                  ))}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {undated.length > 0 && (
        <div className="calendar-undated">
          <h3>No close date ({undated.length})</h3>
          <p>
            A calendar cannot place these. They are still yours, and still in
            every other view.
          </p>
          <div className="calendar-undated-chips">
            {undated.map((opportunity) => (
              <CalendarChip
                key={opportunity.id}
                opportunity={opportunity}
                selected={selectedId === opportunity.id}
                focused={focusedId === opportunity.id}
                checked={checkedIds.has(opportunity.id)}
                onFocus={onFocus}
                onToggleChecked={onToggleChecked}
                onRangeSelect={onRangeSelect}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

/**
 * One deal in a day cell. The same item the board draws as a card and the
 * list as a row (`useOpportunityItem`), so the cursor, Enter, `x` and
 * shift-click ranges behave identically here — a cell is a smaller drawing of
 * an opportunity, not a different kind of thing.
 */
function CalendarChip({
  opportunity,
  selected,
  focused,
  checked,
  onFocus,
  onToggleChecked,
  onRangeSelect,
}: {
  opportunity: Opportunity;
  selected: boolean;
  focused: boolean;
  checked: boolean;
  onFocus: (opportunity: Opportunity) => void;
  onToggleChecked: (opportunity: Opportunity) => void;
  onRangeSelect: (opportunity: Opportunity) => void;
}) {
  const { itemProps, checkboxProps } = useOpportunityItem({
    className: "opportunity-chip",
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
      <Link to={`/opportunities/${opportunity.id}`}>{opportunity.name}</Link>
      <span className="chip-value">
        {formatMoney(opportunity.currency, opportunity.value)}
      </span>
    </article>
  );
}
