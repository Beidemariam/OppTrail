"use client";

import { Link, useSearchParams } from "react-router";

import {
  calendarWeeks,
  closingOn,
  tasksDueOn,
  formatMoney,
  monthLabel,
  shiftMonth,
  weekdayLabels,
  withoutCloseDate,
  type Task,
  type Opportunity,
} from "../lib/domain";
import { opportunityHref } from "../lib/viewState";
import type { OpportunityViewProps } from "./StageBoard";
import { useOpportunityItem } from "./useOpportunityItem";

/**
 * The calendar view (milestone 2.8): the same filtered opportunities, placed
 * on the month their deal is expected to close.
 *
 * `docs/FEATURES.md` §1 describes it as "expected close dates and follow-up
 * dates" — milestone 3.0b (**D-088**) added the second layer, drawn from
 * `GET /api/v2/timeline/follow-ups`, the cross-opportunity read that did not
 * exist when 2.8 shipped close dates alone. **That layer is tasks since
 * milestone 4.2** (`GET /api/v2/tasks?assignee=any&from=&to=`): a follow-up
 * *is* a task now, the old dates were migrated into tasks by revision
 * `0010_follow_ups_to_tasks`, and the route it used to read is gone. The move
 * was anticipated here, which is why the layer needed no reshaping — only a
 * different source.
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
  tasksDue,
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
  /** The follow-ups due within the drawn grid (milestone 3.0b), already
   * fetched for exactly this range by the dashboard. */
  tasksDue: Task[];
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
              const due = tasksDueOn(tasksDue, day);
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
                  {due.map((task) => (
                    <TaskChip key={task.id} task={task} />
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
  // The board's view state travels with the link (R.1): a deal is its own
  // page now, so the way back has to be able to restore the list.
  const [params] = useSearchParams();
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
      <Link to={opportunityHref(opportunity.id, params)}>
        {opportunity.name}
      </Link>
      <span className="chip-value">
        {formatMoney(opportunity.currency, opportunity.value)}
      </span>
    </article>
  );
}

/**
 * One follow-up due on a day (milestone 3.0b, D-088). Unlike `CalendarChip`
 * this is not an opportunity item: it carries no checkbox, no keyboard
 * cursor and no selection, because a follow-up is a timeline entry, and this
 * app's cross-opportunity reads stop at "here is the opportunity it happened
 * on" (the same granularity `app/SearchPage.tsx` and the activity log use).
 * The link goes to that opportunity's own timeline, not to the entry itself
 * — nothing else in the app deep-links to one entry either.
 */
/** A task due on this day (milestone 4.2), where a follow-up date used to be.
 *
 * The link carries `?entry=` when the task came from an entry, which is how a
 * migrated follow-up still reaches the conversation that produced it (D-124's
 * shape); a task written by hand links to its deal. */
function TaskChip({ task }: { task: Task }) {
  return (
    <article className="followup-chip">
      <Link
        to={
          task.entry_id
            ? `/opportunities/${task.opportunity_id}?entry=${task.entry_id}`
            : `/opportunities/${task.opportunity_id}`
        }
      >
        {task.title}
      </Link>
      <span className="chip-opportunity">{task.opportunity_name}</span>
      {task.assignees.length > 0 && (
        <span className="chip-opportunity">
          {task.assignees.map((item) => item.name).join(", ")}
        </span>
      )}
    </article>
  );
}
