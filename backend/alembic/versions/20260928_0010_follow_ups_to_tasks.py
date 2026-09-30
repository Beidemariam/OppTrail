"""Existing follow-up dates become tasks

Milestone 4.2 (`docs/ROADMAP.md` Phase 4). `docs/FEATURES.md` §8 says "the
existing `follow_up_date` on entries migrates into this model", and this is that
migration: every live entry carrying a date gets one task.

**The column stays.** `docs/ROADMAP.md`'s breaking-changes table keeps it for a
phase and drops it in 6, so nothing here is destructive and a mistake in this
revision costs a `DELETE` of the rows it wrote rather than a restore from
backup.

What each field of the new task is taken from, and why:

- **`title`** is `Follow up: <the entry's title>`. The entry's title says what
  *happened* ("Formal consultancy offer submitted"); a task says what to *do*,
  and the prefix is the smallest honest way to turn one into the other without
  inventing words nobody wrote.
- **`assignee_id` and `created_by`** are both the entry's author. They are the
  person who set the date, which is the only evidence in the row of whose
  follow-up it is. An unassigned task would be nobody's, and My Tasks would show
  it to no one.
- **`entry_id`** is the source entry, so the task links back to why it exists
  and the reader can read the conversation it came from.
- **`created_at`/`updated_at`** are the *entry's* `created_at`, not this
  migration's clock. The intent was recorded then; stamping it now would sort
  every migrated task together at the top of any history that orders by
  creation, which is a claim about when somebody decided something.

Two guards inside the query rather than in application code, because a revision
cannot import application code (the reason `make reindex` duplicates its SQL):

- `deleted_at IS NULL` on the entry **and** on its opportunity, so a follow-up
  on a deleted deal does not come back as a live task.
- `NOT EXISTS` against `tasks`, so a database where somebody has already made
  the task by hand does not get a duplicate. It also makes this revision safe to
  re-run by hand against a partially-migrated copy, which is what an operator
  reaching for it would actually do.

Revision ID: 0010_follow_ups_to_tasks
Revises: 0009_tasks
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_follow_ups_to_tasks"
down_revision: str | None = "0009_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO tasks (
            opportunity_id, entry_id, title, assignee_id, due_date,
            created_by, created_at, updated_at
        )
        SELECT
            timeline_entries.opportunity_id,
            timeline_entries.id,
            'Follow up: ' || timeline_entries.title,
            timeline_entries.created_by,
            timeline_entries.follow_up_date,
            timeline_entries.created_by,
            timeline_entries.created_at,
            timeline_entries.created_at
        FROM timeline_entries
        JOIN opportunities ON opportunities.id = timeline_entries.opportunity_id
        WHERE timeline_entries.follow_up_date IS NOT NULL
            AND timeline_entries.deleted_at IS NULL
            AND opportunities.deleted_at IS NULL
            AND timeline_entries.created_by IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM tasks
                WHERE tasks.entry_id = timeline_entries.id
                    AND tasks.deleted_at IS NULL
            )
        """
    )


def downgrade() -> None:
    # Only what this revision could have written: a task that names an entry and
    # repeats its follow-up date. A task somebody wrote by hand against the same
    # entry has its own title and is left alone.
    op.execute(
        """
        DELETE FROM tasks
        WHERE entry_id IS NOT NULL
            AND title = (
                SELECT 'Follow up: ' || timeline_entries.title
                FROM timeline_entries
                WHERE timeline_entries.id = tasks.entry_id
            )
            AND due_date = (
                SELECT timeline_entries.follow_up_date
                FROM timeline_entries
                WHERE timeline_entries.id = tasks.entry_id
            )
        """
    )
