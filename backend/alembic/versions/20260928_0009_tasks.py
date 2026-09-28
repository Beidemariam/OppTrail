"""Tasks scoped to an opportunity

Milestone 4.1 (`docs/ROADMAP.md` Phase 4, `docs/FEATURES.md` §8). One table,
deliberately the smallest thing that satisfies the requirement: "action items
scoped to an opportunity: title, assignee, due date, done state, optional link
to the entry that prompted it." §8 also says what this is not -- "no subtasks,
no dependencies, no time tracking, no sprints" -- so there is no parent column
here, and no room for one to be added by accident.

Four shapes worth explaining, each of them a pattern this schema already uses
somewhere else:

- **`completed_at` is the done state**, nullable, `NULL` meaning open, with
  `completed_by` beside it. A boolean would answer "is it done" and nothing
  else; a timestamp answers "when" and "who" for free, and the pair is exactly
  what revision 0003 did for `notifications.read_at` after the boolean `read`
  turned out to be the poorer column (D-095). Marking a done task done again
  is idempotent because the route writes through `COALESCE`.
- **`assignee_id` is nullable.** §8 lists an assignee but an action item
  written down before it is handed to anyone is the common case, and a task
  nobody owns is still a task. `ON DELETE` is not specified anywhere in this
  schema because nothing is hard-deleted (invariant 5).
- **`entry_id` is the optional link to the entry that prompted it**, and the
  route -- not the schema -- enforces that the entry belongs to the same
  opportunity. A foreign key cannot express that, and the same rule applies to
  a comment's parent for the same reason (D-127).
- **`due_date` is a date, not a timestamp**: `YYYY-MM-DD`, validated by
  `schemas.canonical_date` like `opportunities.expected_close_date` and
  `timeline_entries.follow_up_date`. "Call them back Thursday" has no time of
  day, and a date sorts and range-filters lexicographically the same way
  (invariant 1).

`tasks` **is** in `app.soft_delete.USER_DATA_TABLES`, unlike `reactions` and
`watchers` from revision 0008. A task is content -- somebody wrote it down and
a colleague may be relying on it -- not toggle state, so deleting one is a soft
delete with an audit row and an Undo, and completing one is not a delete at
all.

Revision ID: 0009_tasks
Revises: 0008_reactions_watchers
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_tasks"
down_revision: str | None = "0008_reactions_watchers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            entry_id INTEGER REFERENCES timeline_entries(id),
            title TEXT NOT NULL,
            assignee_id INTEGER REFERENCES users(id),
            due_date TEXT,
            completed_at TEXT,
            completed_by INTEGER REFERENCES users(id),
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT
        )
        """
    )
    # One opportunity's task list, which is how the per-opportunity surface
    # reads them. Every paginated ORDER BY in this app ends in the row id
    # (`pagination.py`), so the index does too.
    op.execute(
        """
        CREATE INDEX idx_tasks_opportunity
            ON tasks (opportunity_id, due_date, id)
        """
    )
    # My Tasks, which reads across opportunities by assignee and is the one
    # query here that cannot resolve a single role first -- so it filters
    # inside the query like search does, and this index is what keeps that
    # cheap.
    op.execute(
        """
        CREATE INDEX idx_tasks_assignee
            ON tasks (assignee_id, completed_at, due_date, id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tasks_assignee")
    op.execute("DROP INDEX IF EXISTS idx_tasks_opportunity")
    op.execute("DROP TABLE IF EXISTS tasks")
