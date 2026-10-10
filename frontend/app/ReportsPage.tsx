"use client";

import { useId, useState, type ReactNode } from "react";
import { Link } from "react-router";

import {
  activityByRep,
  activityWeeks,
  formatMoney,
  stageDurationText,
  weekLabel,
  winRatePercent,
  type Dashboard,
} from "../lib/domain";
import { useDashboard, useSession } from "../lib/queries";
import { formatTimestamp } from "../lib/time";

/**
 * The dashboard at `/reports` (milestone 6.2, `docs/FEATURES.md` §10): "a
 * sales manager needs to know pipeline value, what is stuck, and what closed,
 * without opening twenty opportunities one at a time."
 *
 * Six aggregations, computed live by the API and drawn here. Four things about
 * the shape:
 *
 * - **It is a screen, not a panel.** The board answers "what is happening on
 *   this deal"; this answers a question about every deal at once, which is
 *   the same split `/tasks` already makes.
 * - **`/reports`, not `/dashboard`.** The board at `/` is what this app's own
 *   code and docs have always called the dashboard (`app/DashboardPage.tsx`),
 *   so reusing the word for a second screen would make every reference
 *   ambiguous. The API route keeps `dashboard` because that is what §10 calls
 *   the feature.
 * - **Numbers are drawn as bars made of CSS**, not as a charting library.
 *   Six aggregations at this scale need a width and a label; a dependency
 *   that renders axes is weight this does not need, and D-073's rule applies
 *   — a primitive arrives with the milestone that has a caller for it.
 * - **A metric that cannot be computed says so.** Time in stage prints how
 *   far back it can be trusted, and an unmeasured stage reads "not yet
 *   measured" rather than "0 days" (§10's own caveat). A win rate with
 *   nothing closed reads "nothing closed yet", not "0%".
 */
/**
 * The period, and the window each choice gives the two metrics that have one.
 *
 * Four of the six describe the pipeline **as it stands now** and have no
 * period to apply: a stage's deal count, a forecast, what has gone quiet
 * (which carries its own fixed 14-day rule), and time in stage (which covers
 * all recorded history and says how far back that reaches). Only win/loss and
 * activity-per-rep are windowed.
 *
 * That was the defect the human found at the 6.2 review -- *"even when I pick
 * 30 days, the activity per person shows last 8 weeks, so verify if the
 * filter impacts all reported fields"*. The control drove win/loss alone
 * while being labelled as though it drove everything. It now drives both
 * windowed metrics, **and every card states the window it actually used**,
 * which is the half that was missing: a control whose scope is invisible is a
 * control that has to be guessed at.
 *
 * `weeks` is capped at the API's own 52, because a per-week series cannot be
 * unbounded -- "All time" gives activity a year, and the card says so rather
 * than claiming all of it.
 */
const PERIODS: { label: string; days: number | null; weeks: number }[] = [
  { label: "All time", days: null, weeks: 52 },
  { label: "Last 90 days", days: 90, weeks: 13 },
  { label: "Last 30 days", days: 30, weeks: 4 },
];

/** `since` as the API wants it: a date, or empty for all time. */
function sinceFor(days: number | null): string {
  if (days === null) {
    return "";
  }
  const floor = new Date(Date.now() - days * 86400 * 1000);
  return floor.toISOString().slice(0, 10);
}

export function ReportsPage() {
  const session = useSession();
  const [periodDays, setPeriodDays] = useState<number | null>(null);
  const period =
    PERIODS.find((candidate) => candidate.days === periodDays) ?? PERIODS[0];
  const dashboard = useDashboard(
    sinceFor(periodDays),
    period.weeks,
    Boolean(session.data),
  );

  if (session.isPending) {
    return (
      <main className="app-shell">
        <p className="status">Loading...</p>
      </main>
    );
  }

  if (!session.data) {
    return (
      <main className="app-shell">
        <header className="topbar">
          <div>
            <p className="eyebrow">OppTrail</p>
            <h1>Reports</h1>
          </div>
        </header>
        <p className="empty-state">
          <Link to="/">Sign in</Link> to see your pipeline.
        </p>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">OppTrail</p>
          <h1>Reports</h1>
        </div>
        <div className="user-block">
          <span>{session.data.name}</span>
          <Link className="secondary-button" to="/">
            Opportunities
          </Link>
        </div>
      </header>

      <section className="workspace">
        <div className="page-actions">
          <label className="filter-field">
            Period
            <select
              aria-label="Win and loss period"
              value={periodDays === null ? "" : String(periodDays)}
              onChange={(event) =>
                setPeriodDays(
                  event.target.value === "" ? null : Number(event.target.value),
                )
              }
            >
              {PERIODS.map((option) => (
                <option
                  key={option.label}
                  value={option.days === null ? "" : String(option.days)}
                >
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <p className="report-note">
          The period applies to <strong>Win and loss</strong> and{" "}
          <strong>Activity per person</strong>. The other four describe your
          pipeline as it stands now.
        </p>

        {dashboard.isError && (
          <p className="error">{dashboard.error.message}</p>
        )}
        {dashboard.isPending && <p className="status">Loading reports...</p>}
        {dashboard.data && <Reports data={dashboard.data} period={period} />}
      </section>
    </main>
  );
}

/**
 * One report, as a named landmark.
 *
 * `aria-labelledby` rather than a bare `<section>` with an `<h2>` in it: a
 * section is only a `region` once it has an accessible name, and six unnamed
 * sections are six things a screen-reader user cannot navigate between or
 * tell apart. The heading is already on screen, so pointing at it is both the
 * correct wiring and free.
 */
function ReportCard({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: string;
  children: ReactNode;
}) {
  const headingId = useId();
  return (
    <section className="report-card" aria-labelledby={headingId}>
      <div className="section-heading">
        <h2 id={headingId}>{title}</h2>
        {meta !== undefined && <span>{meta}</span>}
      </div>
      {children}
    </section>
  );
}

function Reports({
  data,
  period,
}: {
  data: Dashboard;
  period: (typeof PERIODS)[number];
}) {
  /**
   * A summed figure, labelled with the currency it is actually in.
   *
   * The API answers `currency: null` when the deals it summed carry more than
   * one, because then the total is a number and not an amount (milestone
   * 6.2). Stamping a symbol on that would be the screen telling a lie the API
   * went out of its way to avoid.
   */
  const money = (value: string) =>
    data.currency
      ? formatMoney(data.currency, value)
      : `${Number(value).toLocaleString("en-US")} (mixed currencies)`;

  const biggestStage = Math.max(
    1,
    ...data.pipeline.map((stage) => Number(stage.value)),
  );
  const weeks = activityWeeks(data.activity);
  const reps = activityByRep(data.activity);
  const busiestWeek = Math.max(1, ...data.activity.map((row) => row.items));
  const winRate = winRatePercent(data.win_loss.rate);

  return (
    <>
      <ReportCard
        title="Pipeline by stage"
        meta={`${data.pipeline.reduce((total, s) => total + s.deals, 0)} open`}
      >
        <ul className="bar-list">
          {data.pipeline.map((stage) => (
            <li key={stage.stage}>
              <span className="bar-label">{stage.stage}</span>
              <span className="bar-track">
                <span
                  className="bar-fill"
                  style={{
                    width: `${(Number(stage.value) / biggestStage) * 100}%`,
                  }}
                />
              </span>
              <span className="bar-value">
                {money(stage.value)}
                <small>
                  {stage.deals} {stage.deals === 1 ? "deal" : "deals"}
                </small>
              </span>
            </li>
          ))}
        </ul>
      </ReportCard>

      <div className="report-row">
        <ReportCard title="Win and loss" meta={period.label.toLowerCase()}>
          {winRate === null ? (
            <p className="empty-state">
              Nothing closed yet in this period, so there is no win rate to
              show.
            </p>
          ) : (
            <>
              <p className="report-figure">{winRate}</p>
              <p className="report-note">
                {data.win_loss.won} won, {data.win_loss.lost} lost
                {" · "}
                {money(data.win_loss.won_value)} won
              </p>
            </>
          )}
        </ReportCard>

        <ReportCard title="Forecast">
          <p className="report-figure">{money(data.forecast.weighted_value)}</p>
          <p className="report-note">
            Each open stage at its own probability, so the assumptions are
            visible rather than implied:
          </p>
          <ul className="assumption-list">
            {data.forecast.stages.map((stage) => (
              <li key={stage.stage}>
                <span>{stage.stage}</span>
                <span>{Math.round(stage.probability * 100)}%</span>
                <span>{money(stage.weighted_value)}</span>
              </li>
            ))}
          </ul>
        </ReportCard>
      </div>

      <ReportCard title="Average time in stage">
        {/* §10: this is "only correct back to the point stage-change entries
            began being recorded; earlier history is absent and should be
            labelled as such rather than silently shown as zero." */}
        <p className="report-note">
          {data.time_in_stage.earliest_change
            ? `Measured from stage changes recorded since ${formatTimestamp(
                data.time_in_stage.earliest_change,
              )}. Anything before that is not in this database.`
            : "No stage change has been recorded yet, so there is nothing to measure."}
        </p>
        <ul className="assumption-list">
          {data.time_in_stage.stages.map((stage) => (
            <li key={stage.stage}>
              <span>{stage.stage}</span>
              <span>{stageDurationText(stage.average_days)}</span>
              <span>
                {stage.spans === 0
                  ? ""
                  : `${stage.spans} ${stage.spans === 1 ? "move" : "moves"}`}
              </span>
            </li>
          ))}
        </ul>
      </ReportCard>

      <ReportCard title="Gone quiet" meta={String(data.stalled.length)}>
        {data.stalled.length === 0 ? (
          <p className="empty-state">Nothing has been silent for 14 days.</p>
        ) : (
          <ul className="stalled-list">
            {data.stalled.map((deal) => (
              <li key={deal.opportunity_id}>
                <Link to={`/opportunities/${deal.opportunity_id}`}>
                  {deal.name}
                </Link>
                <span>{deal.stage}</span>
                <span>{money(deal.value)}</span>
                <span>
                  Last activity {formatTimestamp(deal.last_activity_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </ReportCard>

      <ReportCard
        title="Activity per person"
        meta={`last ${period.weeks} weeks`}
      >
        {reps.length === 0 ? (
          <p className="empty-state">
            Nothing has been logged in the last eight weeks.
          </p>
        ) : (
          <ul className="bar-list">
            {reps.map((rep) => (
              <li key={rep.authorId}>
                <span className="bar-label">{rep.authorName}</span>
                <span className="spark">
                  {weeks.map((week) => {
                    const items = rep.weeks.get(week) ?? 0;
                    return (
                      <span
                        className="spark-bar"
                        key={week}
                        style={{ height: `${(items / busiestWeek) * 100}%` }}
                        title={`${weekLabel(week)}: ${items}`}
                      />
                    );
                  })}
                </span>
                <span className="bar-value">
                  {[...rep.weeks.values()].reduce((a, b) => a + b, 0)}
                  <small>items</small>
                </span>
              </li>
            ))}
          </ul>
        )}
      </ReportCard>
    </>
  );
}
