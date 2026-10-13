"""What the scheduler runs, and the record of its having run.

Milestone 6.5, ADR 0004. The ADR's last line is the design rule here: *"Keep
job functions free of framework coupling so they stay directly testable."* So
this module knows nothing about APScheduler — `scheduler.py` is the only thing
that does — and every function below is callable from a test, from a route, or
from a timer with the same result.

Two jobs, which is all of v2's recurring work:

- **`run_automations`** evaluates the two of §11's five triggers that the
  clock owns, `no_activity` and `close_date_approaching`. It calls
  `automations.run_rule`, the same function `POST /automation-rules/{id}/run`
  calls, so there is one evaluator and a tick cannot drift from a manual run
  (**D-175**).
- **`run_backup`** is ADR 0011's `VACUUM INTO` snapshot, which has waited for
  a schedule since milestone 1.6 — until now it ran only when somebody typed
  `make backup`.

**Every run is recorded** (`job_runs`), because a scheduler that stops is
invisible: nothing errors and nothing 500s, the rules just never fire again
(`docs/ARCHITECTURE.md`, Observability). The row is written when the job
*starts* and updated when it ends, so a row left at `started` is the signature
of a process that died mid-job.

**A failing job is recorded, not raised.** There is no caller to answer: a
tick that raises would be swallowed by APScheduler's own logging and the next
tick would run regardless. The row is the report.
"""

import sqlite3
from collections.abc import Callable
from typing import Literal

from .automations import RULE_ROWS_SQL, TIME_TRIGGERS, rule_from_row, run_rule
from .backup import create_backup
from .database import db_connection
from .logging_utils import logger
from .schemas import JobRunPublic
from .time_utils import utc_now

JobName = Literal["automations", "backup"]

JOB_ROWS_SQL = """
    SELECT id, job, status, detail, started_at, finished_at
    FROM job_runs
"""


def start_job(connection: sqlite3.Connection, job: JobName) -> int:
    cursor = connection.execute(
        """
        INSERT INTO job_runs (job, status, started_at)
        VALUES (?, 'started', ?)
        """,
        (job, utc_now()),
    )
    connection.commit()
    return int(cursor.lastrowid or 0)


def finish_job(
    connection: sqlite3.Connection,
    run_id: int,
    status: Literal["succeeded", "failed"],
    detail: str,
) -> None:
    connection.execute(
        """
        UPDATE job_runs
        SET status = ?, detail = ?, finished_at = ?
        WHERE id = ?
        """,
        (status, detail[:500], utc_now(), run_id),
    )
    connection.commit()


def latest_job_runs(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """The most recent run of each job, for `/api/health`.

    One row per job rather than the whole log: a probe answers "is the
    scheduler alive", and the answer is the newest row's time and status.
    """
    return list(
        connection.execute(
            f"""
            {JOB_ROWS_SQL}
            WHERE id IN (SELECT MAX(id) FROM job_runs GROUP BY job)
            ORDER BY job
            """
        ).fetchall()
    )


def run_automations() -> str:
    """Evaluate every armed rule the clock owns. Returns what it did.

    Opens its own connection and commits as it goes, like a route handler:
    there is no request here, and `database.py` has no pool to borrow from.

    Rules are read whole into memory before any is evaluated. A tick walks at
    most `MAX_ENABLED_RULES_PER_CREATOR` per person, and evaluating one writes
    to the tables the query reads from -- so holding a cursor open across the
    loop would be reading a list that the loop is changing underneath it.
    """
    with db_connection() as connection:
        placeholders = ",".join("?" for _ in TIME_TRIGGERS)
        rows = connection.execute(
            f"""
            {RULE_ROWS_SQL}
            WHERE automation_rules.trigger_type IN ({placeholders})
                AND automation_rules.archived_at IS NULL
                AND automation_rules.enabled = 1
            ORDER BY automation_rules.id
            """,
            TIME_TRIGGERS,
        ).fetchall()

        considered = 0
        applied = 0
        skipped = 0
        for row in rows:
            rule = rule_from_row(row)
            seen, run_ids = run_rule(connection, rule, dry_run=False)
            connection.commit()
            considered += seen
            # Counted by outcome rather than by row, because a run row is also
            # written for a deal the rule *declined* to act on -- the creator
            # lacked the role, or the rule had already acted inside its window.
            # The first version of this line counted both as "acted on", and
            # the live scheduler duly reported "2 deals considered, 2 acted on"
            # for a tick that wrote nothing at all. A detail line nobody can
            # trust is worse than no detail line.
            acted = count_applied(connection, run_ids)
            applied += acted
            skipped += len(run_ids) - acted

    return (
        f"{len(rows)} rules, {considered} deals considered, {applied} acted on, {skipped} skipped"
    )


def count_applied(connection: sqlite3.Connection, run_ids: list[int]) -> int:
    if not run_ids:
        return 0
    placeholders = ",".join("?" for _ in run_ids)
    return int(
        connection.execute(
            f"""
            SELECT COUNT(*) AS applied FROM automation_runs
            WHERE id IN ({placeholders}) AND outcome = 'applied'
            """,
            run_ids,
        ).fetchone()["applied"]
    )


def run_backup() -> str:
    """ADR 0011's snapshot, unattended at last.

    `create_backup` prunes to `backup_retention_count` itself, so there is
    nothing to add here: the schedule is the whole of what was missing.
    """
    return create_backup().name


JOBS: dict[JobName, Callable[[], str]] = {
    "automations": run_automations,
    "backup": run_backup,
}


def run_job(job: JobName) -> None:
    """One job, recorded start to finish, raising nothing.

    This is what the scheduler calls. The `except` is deliberately broad and
    the reason is the one `fire_event_after_commit` gives for its own: there
    is nobody to answer. A tick that raised would be logged by APScheduler and
    lost; here the failure lands in the table a person can read, and the next
    tick runs anyway because periodic jobs are idempotent (ADR 0004).
    """
    with db_connection() as connection:
        run_id = start_job(connection, job)

    try:
        detail = JOBS[job]()
    except Exception as exc:  # noqa: BLE001 - see the docstring
        logger.error("job_failed", exc_info=exc, extra={"job": job})
        with db_connection() as connection:
            finish_job(connection, run_id, "failed", f"{type(exc).__name__}: {exc}")
        return

    logger.info("job_succeeded", extra={"job": job, "detail": detail})
    with db_connection() as connection:
        finish_job(connection, run_id, "succeeded", detail)


def job_run_from_row(row: sqlite3.Row) -> JobRunPublic:
    return JobRunPublic(
        id=row["id"],
        job=row["job"],
        status=row["status"],
        detail=row["detail"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )
