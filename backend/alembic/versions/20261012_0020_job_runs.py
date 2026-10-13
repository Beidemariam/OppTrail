"""The scheduler's own log: one row per execution of a periodic job

Milestone 6.5, ADR 0004. `docs/ARCHITECTURE.md`'s Observability section is
explicit about why this table exists and not merely that it does: *"a silently
dead scheduler is the most likely v2 production failure"*. A scheduler that
stops is invisible — nothing errors, nothing 500s, the rules simply never fire
again — so the only way to know it is alive is a row it writes when it runs.

- **A row is written when a job starts, not when it finishes.** `status` goes
  `started` then `succeeded` or `failed`. A row left at `started` is the
  signature of a process that died mid-job, which is the one failure a
  finished-only log cannot show.
- **`detail` is what the run did**, in the job's own words — "4 rules
  evaluated, 2 deals acted on", a backup's path, or an exception's message.
  Free text and not JSON: nothing queries it, a person reads it.
- **This is not ADR 0004's `outbox`.** The ADR describes two things and this
  is the smaller one: a record of periodic work. The outbox — durable rows
  claimed with a status transition so deferred work survives a restart —
  waits for v3 with the first thing that sends an email, because nothing in
  v2 sends anything (**D-141**).

Not pruned. A row per job per tick is ~100 rows a day at the shipped
intervals, and the table carries no user data, so a retention rule would be
machinery for a problem that arrives in years. `backup_retention_count`
prunes snapshots because those are megabytes each; these are bytes.

Revision ID: 0020_job_runs
Revises: 0019_automation_run_entry_index
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_job_runs"
down_revision: str | None = "0019_automation_run_entry_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE job_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job TEXT NOT NULL CHECK (job IN ('automations', 'backup')),
            status TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'failed')),
            detail TEXT,
            started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            finished_at TEXT
        )
        """
    )
    # Both reads are "the latest runs, newest first" -- the whole log for the
    # screen, and the latest row per job for `/api/health`. Descending, which
    # is the one place in this schema an index is not ascending: this table is
    # read from the present backwards, unlike every paginated collection.
    op.execute(
        """
        CREATE INDEX idx_job_runs_latest
        ON job_runs (job, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_job_runs_latest")
    op.execute("DROP TABLE IF EXISTS job_runs")
