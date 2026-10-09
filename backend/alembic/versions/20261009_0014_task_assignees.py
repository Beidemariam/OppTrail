"""More than one person on a task

Milestone 4.6, the other half of the human's "build both" ruling at the Phase 4
gate (**D-146**). `tasks.assignee_id` holds one person; real work is handed to
two.

Three changes, and the second is the one with teeth:

- **`task_assignees`** is the truth from here on: one row per (task, person),
  unique on the pair, so adding somebody twice is a no-op rather than a second
  row. Backfilled from every live task's `assignee_id`.
- **`task_versions.assignee_ids`** is how a snapshot records a *set*. The
  history has to keep reading (D-097: a version is what this database can still
  show), so the old `assignee_id` column stays exactly as written and the new
  one is backfilled from it -- a one-person task's history is unchanged in
  meaning, and every version written from now on carries the whole list. The
  format is the canonical one `routes_tasks.TASK_ROWS_SQL` produces: user ids
  ascending, comma separated, `NULL` for nobody, so two snapshots of the same
  people compare equal and `versioning.version_is_current` keeps working
  without knowing what the string means.
- **`tasks.assignee_id` is left in place and stops being read.** The pattern
  `follow_up_date` already follows (`docs/ROADMAP.md`'s breaking-changes table):
  a column outlives its readers by a phase so a rollback has somewhere to land,
  and it is dropped in Phase 6 with that one. Nothing writes it after this
  revision, so unlike the follow-up case it cannot drift -- it is frozen
  history rather than a live field nobody reads (**D-144**'s hazard, avoided
  here by there being no UI that can set it).

Revision ID: 0014_task_assignees
Revises: 0013_task_comments
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_task_assignees"
down_revision: str | None = "0013_task_comments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE task_assignees (
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            PRIMARY KEY (task_id, user_id)
        )
        """
    )
    # My Tasks reads this the other way round -- "what does this person owe",
    # across every deal -- which the primary key above cannot serve.
    op.execute("CREATE INDEX idx_task_assignees_user ON task_assignees (user_id, task_id)")

    # Everyone currently assigned, including on tasks that are done: a history
    # of who owed what is part of what the deal's record says.
    op.execute(
        """
        INSERT INTO task_assignees (task_id, user_id, created_at)
        SELECT id, assignee_id, created_at
        FROM tasks
        WHERE assignee_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM task_assignees
                WHERE task_assignees.task_id = tasks.id
                    AND task_assignees.user_id = tasks.assignee_id
            )
        """
    )

    op.execute("ALTER TABLE task_versions ADD COLUMN assignee_ids TEXT")
    # One id reads as a one-element list, which is what that snapshot always
    # meant; a version recorded with nobody assigned stays NULL.
    op.execute(
        """
        UPDATE task_versions
        SET assignee_ids = CAST(assignee_id AS TEXT)
        WHERE assignee_id IS NOT NULL AND assignee_ids IS NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE task_versions DROP COLUMN assignee_ids")
    op.execute("DROP TABLE IF EXISTS task_assignees")
