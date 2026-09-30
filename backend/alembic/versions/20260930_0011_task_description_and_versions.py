"""A task's description, and its edit history

Milestone 4.2a, from the Phase 4 checkpoint review. Two changes to `tasks`, each
closing a gap in 4.1 rather than adding a feature on top of it:

- **`description`**, asked for at the review. `FEATURES.md` §8 lists a task's
  fields as "title, assignee, due date, done state, optional link to the entry"
  and does not mention one; the human asked for it directly, which outranks the
  feature list (`AGENTS.md`'s source hierarchy). Markdown, like every other body
  in this app, so the composer and the renderer already know how to handle it.
- **`task_versions`**, which `AGENTS.md` invariant 8 already required and
  milestone 4.1 did not build: "every user-editable field keeps its previous
  value, attributed to who changed it and when, and the opportunity owner can
  read that history in the UI." A task's title, description, assignee and due
  date are all editable, so the invariant applies to them exactly as it does to
  an opportunity's fields. The human asked for this too, independently.

The version table is the fourth of the identical shape `versioning.py` describes
-- `note_versions`, `opportunity_versions`, `timeline_entry_versions` and now
this -- and it is added there as a `VersionedTable` rather than as a fourth
INSERT, which is what that module exists to prevent.

**`completed_at` is deliberately not a versioned field.** Ticking a task off and
reopening it is toggle state a person sets and unsets, not a value they wrote --
the same reasoning that keeps `reactions` and `watchers` out of the soft-delete
tables (D-130). A history of every time a task was checked and unchecked is a log
nobody reads; what invariant 8 protects is content quietly rewritten.

**Every existing task gets version 1**, from its current values, for the reason
revision 0006 gave the other three tables (**D-097**): a row that predates this
revision has no earlier state to recover, so version 1 reads as the oldest state
this database can still show rather than as a recorded edit. Without it, the
first edit after the upgrade would be a history with nothing to read it against.

Revision ID: 0011_task_description_and_versions
Revises: 0010_follow_ups_to_tasks
Create Date: 2026-09-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_task_description_and_versions"
down_revision: str | None = "0010_follow_ups_to_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT ''")

    op.execute(
        """
        CREATE TABLE task_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            version_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            assignee_id INTEGER REFERENCES users(id),
            due_date TEXT,
            edited_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            UNIQUE (task_id, version_number)
        )
        """
    )
    # Read oldest-first per task, like the other three histories; the unique
    # index above already leads on `task_id`, so it serves the lookup.

    # Version 1 for everything already here (D-097). `created_by` is the editor
    # of record: nobody else can have written the row's current values, and the
    # stamp is the task's own `updated_at` rather than now, so the baseline does
    # not claim an edit happened at upgrade time.
    op.execute(
        """
        INSERT INTO task_versions (
            task_id, version_number, title, description, assignee_id, due_date,
            edited_by, created_at
        )
        SELECT id, 1, title, description, assignee_id, due_date, created_by, updated_at
        FROM tasks
        WHERE deleted_at IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM task_versions WHERE task_versions.task_id = tasks.id
            )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS task_versions")
    # SQLite can drop a column since 3.35, and the version guard
    # (`scripts/check-sqlite-version.sh`) floors well above that.
    op.execute("ALTER TABLE tasks DROP COLUMN description")
