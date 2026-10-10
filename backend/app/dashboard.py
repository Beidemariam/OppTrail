"""The six aggregations `docs/FEATURES.md` §10 names, computed live.

Milestone 6.2. The spec is explicit about the shape: "at 400 opportunities and
~800,000 activity rows these remain single indexed aggregate queries --
computed live, **no rollup tables, no materialized views, no warehouse**", and
each one has to answer inside 300 ms, asserted in CI.

Three things run through all six:

- **Permissions live inside the query**, not as a filter over its results.
  This is the second read in the app that spans opportunities (search was the
  first), so it cannot resolve a role first the way every per-record route
  does: it takes `permissions.ACCESSIBLE_OPPORTUNITY_IDS_SQL` as a subquery
  and every number is therefore already a number this caller may see. Two
  managers asking the same question get different answers, which is correct.
- **Every date is compared as text.** Timestamps are fixed-width UTC
  (`time_utils.py`), so a period filter is a string comparison and a week
  bucket is `substr`/`strftime` over the stored value -- no parsing, no
  timezone, and the index is usable.
- **A metric that cannot be computed says so** rather than answering zero.
  Average time in stage is the one the spec singles out: it is only correct
  back to the point stage-change entries began being recorded, so the
  response carries `earliest_stage_change` and the screen labels it.
"""

import sqlite3
from decimal import Decimal

from .permissions import ACCESSIBLE_OPPORTUNITY_IDS_SQL
from .schemas import (
    STAGES,
    Forecast,
    ForecastStage,
    PipelineStage,
    RepActivity,
    StageDuration,
    StalledOpportunity,
    TimeInStage,
    WinLoss,
)
from .settings import settings
from .time_utils import utc_days_ago

# The 14-day rule the board already applies per card
# (`routes_opportunities.is_opportunity_stalled`), read here across every deal
# the caller can see. One definition would be better than two; the per-card one
# answers "is this deal stalled" for one id and this answers "which are", and
# the shared part is the constant below rather than the query.
STALLED_AFTER_DAYS = 14

CLOSED_STAGES = ("Closed Won", "Closed Lost")
OPEN_STAGES = [stage for stage in STAGES if stage not in CLOSED_STAGES]

# How much of a deal's value a stage is worth, for the forecast. Configurable
# per deployment (`settings.forecast_probabilities`), because the right ramp is
# a property of a sales process rather than of this software -- these defaults
# are a straight ramp to 1.0 at Closed Won, which is the least surprising thing
# to show somebody who has not configured it.
DEFAULT_FORECAST_PROBABILITIES: dict[str, float] = {
    "Prospecting": 0.1,
    "Qualification": 0.2,
    "Needs Analysis": 0.4,
    "Proposal": 0.6,
    "Negotiation": 0.8,
    "Closed Won": 1.0,
    "Closed Lost": 0.0,
}


def forecast_probabilities() -> dict[str, float]:
    """The configured ramp, with any stage the configuration omits falling
    back to its default -- so a deployment can tune two stages without having
    to restate the other five."""
    return {**DEFAULT_FORECAST_PROBABILITIES, **settings.forecast_probabilities}


def _accessible(user_id: int) -> tuple[str, list[object]]:
    """The predicate and its parameters, for a metric to embed in a `WHERE`."""
    return f"opportunities.id IN ({ACCESSIBLE_OPPORTUNITY_IDS_SQL})", [
        user_id,
        user_id,
    ]


def _accessible_cte(user_id: int) -> tuple[str, list[object]]:
    """The same set as a **materialized** CTE, opening a `WITH` the caller
    continues.

    For a metric that joins the set three times -- `activity_per_rep` -- the
    predicate form above makes SQLite re-derive it per branch, and
    `MATERIALIZED` is what stops that. It is spelled out rather than left to
    the planner because the 300 ms budget turns on it (**D-172**).
    """
    return f"WITH accessible AS MATERIALIZED ({ACCESSIBLE_OPPORTUNITY_IDS_SQL}),", [
        user_id,
        user_id,
    ]


def summed_currency(connection: sqlite3.Connection, user_id: int) -> str | None:
    """The currency every one of these sums is in, or `None` if there is more
    than one.

    Four of the six metrics add `value` across deals, and `opportunities`
    carries a currency per row -- so a deployment holding both USD and EUR
    deals would get a total that is a number and not an amount. Nothing in
    §10 mentions this, and the honest answer is cheap: say which currency the
    sums are in when there is one, and say nothing when there is not, so the
    screen can label the figure "mixed currencies" rather than stamping a
    symbol on a sum that has none.

    Not a per-currency breakdown: that is a reporting feature nobody has
    asked for, and inventing it here would be scope this milestone does not
    own. What this prevents is the sum being *mislabelled*.
    """
    clause, params = _accessible(user_id)
    rows = connection.execute(
        f"""
        SELECT DISTINCT currency FROM opportunities
        WHERE {clause}
        LIMIT 2
        """,
        params,
    ).fetchall()
    return str(rows[0]["currency"]) if len(rows) == 1 else None


def pipeline_by_stage(connection: sqlite3.Connection, user_id: int) -> list[PipelineStage]:
    """Count and value per open stage.

    Closed stages are excluded -- §10's "non-deleted, non-closed" -- because
    pipeline is what might still be won, and a closed deal belongs to the
    win/loss metric instead. Every open stage appears even at zero: a stage
    missing from a pipeline chart reads as a rendering fault rather than as an
    empty column.
    """
    clause, params = _accessible(user_id)
    rows = connection.execute(
        f"""
        SELECT stage, COUNT(*) AS deals, COALESCE(SUM(value), 0) AS value
        FROM opportunities
        WHERE {clause}
            AND stage NOT IN ({", ".join("?" for _ in CLOSED_STAGES)})
        GROUP BY stage
        """,
        (*params, *CLOSED_STAGES),
    ).fetchall()
    found = {row["stage"]: row for row in rows}
    return [
        PipelineStage(
            stage=stage,  # type: ignore[arg-type]
            deals=found[stage]["deals"] if stage in found else 0,
            value=str(Decimal(str(found[stage]["value"]))) if stage in found else "0",
        )
        for stage in OPEN_STAGES
    ]


def win_loss(connection: sqlite3.Connection, user_id: int, since: str | None) -> WinLoss:
    """Closed Won over Closed Won plus Closed Lost, for a period.

    `rate` is `None` rather than 0.0 when nothing closed: a team that has
    closed nothing has no win rate, and showing 0% would read as having lost
    everything.
    """
    clause, params = _accessible(user_id)
    period = "AND opportunities.updated_at >= ?" if since else ""
    row = connection.execute(
        f"""
        SELECT
            SUM(CASE WHEN stage = 'Closed Won' THEN 1 ELSE 0 END) AS won,
            SUM(CASE WHEN stage = 'Closed Lost' THEN 1 ELSE 0 END) AS lost,
            COALESCE(SUM(CASE WHEN stage = 'Closed Won' THEN value ELSE 0 END), 0) AS won_value
        FROM opportunities
        WHERE {clause} {period}
        """,
        (*params, *([since] if since else [])),
    ).fetchone()
    won = int(row["won"] or 0)
    lost = int(row["lost"] or 0)
    closed = won + lost
    return WinLoss(
        won=won,
        lost=lost,
        won_value=str(Decimal(str(row["won_value"]))),
        rate=(won / closed) if closed else None,
    )


def average_time_in_stage(connection: sqlite3.Connection, user_id: int) -> TimeInStage:
    """How long a deal sits in each stage, from the stage-change entries the
    app has recorded since the MVP.

    §10's caveat is the interesting part: this is "only correct back to the
    point stage-change entries began being recorded; earlier history is absent
    and should be labelled as such rather than silently shown as zero". So the
    answer carries `earliest_change`, and a stage with no measurable spans
    answers `null` days rather than `0`.

    The span measured is from one stage change to the next on the same deal,
    which is why the window function is ordered by the entry's own timestamp:
    a backdated stage change belongs where it says it happened.

    **It names its index**, for the same reason `activity_per_rep` does and
    with a sharper lesson behind it (**D-172**). A stage change is a handful
    of rows per deal among hundreds of thousands of entries, so the partial
    index is overwhelmingly the right choice -- but SQLite only chose it on a
    database that had been `ANALYZE`d. On a fresh one it scanned every entry:
    **352 ms** against the 300 ms budget, on the same data that took 2.4 ms
    with the index. Nothing in this application runs `ANALYZE`, so the plan
    that matters is the one without statistics.
    """
    clause, params = _accessible(user_id)
    rows = connection.execute(
        f"""
        WITH changes AS (
            SELECT
                timeline_entries.opportunity_id,
                timeline_entries.event_timestamp AS changed_at,
                timeline_entries.title,
                LEAD(timeline_entries.event_timestamp) OVER (
                    PARTITION BY timeline_entries.opportunity_id
                    ORDER BY timeline_entries.event_timestamp, timeline_entries.id
                ) AS next_changed_at
            FROM timeline_entries INDEXED BY idx_timeline_entries_stage_changes
            JOIN opportunities ON opportunities.id = timeline_entries.opportunity_id
            WHERE timeline_entries.type = 'stage_change'
                AND timeline_entries.deleted_at IS NULL
                AND {clause}
        )
        SELECT
            title,
            AVG(julianday(next_changed_at) - julianday(changed_at)) AS average_days,
            COUNT(*) AS spans,
            MIN(changed_at) AS earliest
        FROM changes
        WHERE next_changed_at IS NOT NULL
        GROUP BY title
        """,
        params,
    ).fetchall()

    # The entry's title is "Stage changed to <stage>", which is the stage the
    # deal moved *into* -- so the span that follows it is time spent in that
    # stage. Parsed rather than stored, because the system entry is the record
    # and adding a column for this would be a second source of the same fact.
    measured: dict[str, tuple[float, int]] = {}
    earliest: str | None = None
    for row in rows:
        stage = str(row["title"]).removeprefix("Stage changed to ").strip()
        if stage in DEFAULT_FORECAST_PROBABILITIES:
            measured[stage] = (round(float(row["average_days"]), 2), int(row["spans"]))
        if row["earliest"] and (earliest is None or row["earliest"] < earliest):
            earliest = row["earliest"]

    return TimeInStage(
        # Every stage, so a chart has an axis -- `null` where nothing has been
        # measured, which the screen labels rather than drawing as zero.
        stages=[
            StageDuration(
                stage=stage,  # type: ignore[arg-type]
                average_days=measured[stage][0] if stage in measured else None,
                spans=measured[stage][1] if stage in measured else 0,
            )
            for stage in STAGES
        ],
        earliest_change=earliest,
    )


def stalled_opportunities(
    connection: sqlite3.Connection,
    user_id: int,
    limit: int = 50,
) -> list[StalledOpportunity]:
    """The 14-day rule as a list, longest-silence-first.

    The same predicate the board applies to one card, asked across every deal
    the caller can read: the latest of any entry, note or comment, compared to
    the cutoff as text. A closed deal is excluded -- it is not stalled, it is
    finished.

    **Written as one grouped pass rather than a correlated subquery**, which
    is a performance fix the 300 ms budget caught rather than a style
    preference. The obvious shape -- `(SELECT MAX(...) WHERE opportunity_id =
    opportunities.id)` -- runs once per deal, and at 400 deals over 200,000
    entries that measured **343 ms**, over budget. Grouping the union once and
    joining it scans each table a single time: **12 ms** on the same data.
    `test_each_aggregate_answers_inside_the_budget` is what keeps it that way.
    """
    clause, params = _accessible(user_id)
    cutoff = utc_days_ago(STALLED_AFTER_DAYS)
    rows = connection.execute(
        f"""
        WITH activity AS (
            SELECT opportunity_id, MAX(activity_at) AS last_activity_at
            FROM (
                SELECT opportunity_id, event_timestamp AS activity_at
                FROM timeline_entries
                WHERE deleted_at IS NULL
                UNION ALL
                SELECT timeline_entries.opportunity_id, notes.created_at
                FROM notes
                JOIN timeline_entries ON timeline_entries.id = notes.entry_id
                WHERE notes.deleted_at IS NULL
                    AND timeline_entries.deleted_at IS NULL
                UNION ALL
                SELECT timeline_entries.opportunity_id, comments.created_at
                FROM comments
                JOIN notes ON notes.id = comments.note_id
                JOIN timeline_entries ON timeline_entries.id = notes.entry_id
                WHERE comments.deleted_at IS NULL
                    AND notes.deleted_at IS NULL
                    AND timeline_entries.deleted_at IS NULL
            )
            GROUP BY opportunity_id
        )
        SELECT
            opportunities.id,
            opportunities.name,
            opportunities.account_name,
            opportunities.stage,
            opportunities.value,
            activity.last_activity_at
        FROM opportunities
        JOIN activity ON activity.opportunity_id = opportunities.id
        WHERE {clause}
            AND opportunities.stage NOT IN ({", ".join("?" for _ in CLOSED_STAGES)})
            AND activity.last_activity_at < ?
        ORDER BY activity.last_activity_at, opportunities.id
        LIMIT ?
        """,
        (*params, *CLOSED_STAGES, cutoff, limit),
    ).fetchall()
    return [
        StalledOpportunity(
            opportunity_id=row["id"],
            name=row["name"],
            account_name=row["account_name"],
            stage=row["stage"],
            value=str(Decimal(str(row["value"]))),
            last_activity_at=row["last_activity_at"],
        )
        for row in rows
    ]


def activity_per_rep(
    connection: sqlite3.Connection,
    user_id: int,
    weeks: int = 8,
) -> list[RepActivity]:
    """Entries, notes and comments by author and week.

    §10 names this as "the one that scans the most rows", and measurement
    agreed emphatically: the obvious formulation took **1,533 ms** against a
    300 ms budget at the spec's own scale. Three things got it to ~20 ms, and
    all three are the kind of detail a budget assertion exists to force
    (**D-172**):

    - **The accessible set is materialized once**, rather than re-derived as
      an `IN (...)` subquery inside each of the three branches.
    - **The index is `(created_at, created_by)`, not `(created_by,
      created_at)`** as §10 suggests. The date is the selective predicate --
      this asks about the last eight weeks -- and the author is only what it
      groups by, so leading with the author makes the range unusable.
    - **The entries branch names its index.** With the join to the accessible
      set in view, SQLite's planner prefers
      `idx_timeline_entries_opportunity_id` and reads every entry ever
      written: 794 ms, against 19 ms when told to seek the date instead, and
      it kept choosing that way after `ANALYZE`. `INDEXED BY` is a planner
      directive and normally a smell, so it is used in exactly the one place
      measurement showed the planner choosing wrong -- the notes and comments
      branches pick the right index unaided and say nothing. It also fails
      *loudly* if that index is ever dropped, which is the right failure for
      something a budget depends on.
    """
    clause, params = _accessible_cte(user_id)
    since = utc_days_ago(weeks * 7)
    rows = connection.execute(
        f"""
        {clause}
        activity AS (
            SELECT timeline_entries.created_by AS author_id,
                   timeline_entries.created_at AS happened_at
            FROM timeline_entries INDEXED BY idx_timeline_entries_created_author
            JOIN accessible ON accessible.id = timeline_entries.opportunity_id
            WHERE timeline_entries.created_at >= ?
                AND timeline_entries.deleted_at IS NULL
                AND timeline_entries.created_by IS NOT NULL
            UNION ALL
            SELECT notes.created_by, notes.created_at
            FROM notes
            JOIN timeline_entries ON timeline_entries.id = notes.entry_id
            JOIN accessible ON accessible.id = timeline_entries.opportunity_id
            WHERE notes.created_at >= ?
                AND notes.deleted_at IS NULL
                AND timeline_entries.deleted_at IS NULL
            UNION ALL
            SELECT comments.created_by, comments.created_at
            FROM comments
            JOIN notes ON notes.id = comments.note_id
            JOIN timeline_entries ON timeline_entries.id = notes.entry_id
            JOIN accessible ON accessible.id = timeline_entries.opportunity_id
            WHERE comments.created_at >= ?
                AND comments.deleted_at IS NULL
                AND notes.deleted_at IS NULL
                AND timeline_entries.deleted_at IS NULL
        )
        SELECT
            activity.author_id,
            users.name AS author_name,
            strftime('%Y-%W', activity.happened_at) AS week,
            COUNT(*) AS items
        FROM activity
        JOIN users ON users.id = activity.author_id
        GROUP BY activity.author_id, week
        ORDER BY week, activity.author_id
        """,
        (*params, since, since, since),
    ).fetchall()
    return [
        RepActivity(
            author_id=row["author_id"],
            author_name=row["author_name"],
            week=row["week"],
            items=int(row["items"]),
        )
        for row in rows
    ]


def forecast(connection: sqlite3.Connection, user_id: int) -> Forecast:
    """Sigma (value x stage probability), with the configured ramp.

    Open stages only, for the reason pipeline excludes closed ones: a forecast
    is about what has not happened yet. The probabilities are returned beside
    the number, because a forecast nobody can see the assumptions of is a
    number nobody should act on.
    """
    clause, params = _accessible(user_id)
    rows = connection.execute(
        f"""
        SELECT stage, COALESCE(SUM(value), 0) AS value
        FROM opportunities
        WHERE {clause}
            AND stage NOT IN ({", ".join("?" for _ in CLOSED_STAGES)})
        GROUP BY stage
        """,
        (*params, *CLOSED_STAGES),
    ).fetchall()
    ramp = forecast_probabilities()
    weighted = Decimal("0")
    per_stage: list[ForecastStage] = []
    for row in rows:
        probability = ramp.get(row["stage"], 0.0)
        stage_value = Decimal(str(row["value"]))
        contribution = stage_value * Decimal(str(probability))
        weighted += contribution
        per_stage.append(
            ForecastStage(
                stage=row["stage"],
                value=str(stage_value),
                probability=probability,
                weighted_value=str(contribution.quantize(Decimal("0.01"))),
            )
        )
    per_stage.sort(key=lambda item: OPEN_STAGES.index(item.stage))
    return Forecast(
        weighted_value=str(weighted.quantize(Decimal("0.01"))),
        stages=per_stage,
    )
