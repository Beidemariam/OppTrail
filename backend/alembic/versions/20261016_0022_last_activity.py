"""When something last happened on a deal, maintained by triggers

Milestone R.3, and the one thing measurement found slow at `AGENTS.md`'s
confirmed scale. The 14-day "stalled" rule asks for the latest of any entry,
note or comment on a deal, and answering it live means a three-way union over
320,000 rows: **63 ms**, paid on every page of the board, which the frontend
reads eight pages of (D-093). Measured on a corpus of 805,220 rows, that was
**60 of the 63 ms** a board page cost — the main query itself is 0.3 ms.

- **Triggers, not application code.** This project already maintains derived
  data this way: nine triggers keep the FTS5 search index in step
  (`20260917_0002_search_index`), for the reason that applies here too — a
  write path added later cannot forget to call something it never knew about.
  There is no `record_activity()` to remember.
- **An insert takes the maximum; an update recomputes.** Writing an entry is
  `MAX(what is there, the new row)`, which is O(1) and keeps a bulk insert
  cheap. A soft delete and an edited `event_timestamp` can both *lower* the
  answer, so those recompute from the union for that one deal — about a
  millisecond, on a path that happens rarely. Getting this the other way
  round would make seeding 80,000 entries take minutes.
- **No DELETE triggers.** Nothing hard-deletes user data in this app
  (`tests/test_soft_delete.py` fails the build if it ever does), so a delete
  arrives as an UPDATE of `deleted_at` and the UPDATE trigger is what answers
  it.
- **`NULL` means nothing has ever happened here**, which is a different fact
  from "happened long ago": a deal created a minute ago is not stalled, and
  the rule reads `last_activity_at < cutoff`, which `NULL` never satisfies.

Revision ID: 0022_last_activity
Revises: 0021_entry_visibility
Create Date: 2026-10-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_last_activity"
down_revision: str | None = "0021_entry_visibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: The latest activity on one deal, as a scalar subquery. Written once here
#: and used by the backfill and by every trigger that has to recompute, so the
#: definition of "activity" cannot differ between them. `app/stalled.py`
#: carries the same union for the one read that still computes it live.
LATEST_ACTIVITY = """
    SELECT MAX(activity_at) FROM (
        SELECT event_timestamp AS activity_at
        FROM timeline_entries
        WHERE opportunity_id = {deal} AND deleted_at IS NULL
        UNION ALL
        SELECT notes.created_at
        FROM notes
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        WHERE timeline_entries.opportunity_id = {deal}
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
        UNION ALL
        SELECT comments.created_at
        FROM comments
        JOIN notes ON notes.id = comments.note_id
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        WHERE timeline_entries.opportunity_id = {deal}
            AND comments.deleted_at IS NULL
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
    )
"""

#: The opportunity a note or a comment belongs to, which neither row carries.
NOTE_DEAL = """
    SELECT opportunity_id FROM timeline_entries WHERE id = (
        SELECT entry_id FROM notes WHERE id = {note}
    )
"""


def upgrade() -> None:
    op.execute("ALTER TABLE opportunities ADD COLUMN last_activity_at TEXT")
    op.execute(
        f"""
        UPDATE opportunities
        SET last_activity_at = ({LATEST_ACTIVITY.format(deal="opportunities.id")})
        """
    )
    # The dashboard's stalled list filters on this column across every
    # accessible deal; the board reads it per row and needs no index for that.
    op.execute(
        """
        CREATE INDEX idx_opportunities_last_activity
        ON opportunities (last_activity_at)
        """
    )

    op.execute(
        """
        CREATE TRIGGER activity_entry_insert AFTER INSERT ON timeline_entries
        WHEN NEW.deleted_at IS NULL
        BEGIN
            UPDATE opportunities
            SET last_activity_at = MAX(
                COALESCE(last_activity_at, NEW.event_timestamp), NEW.event_timestamp
            )
            WHERE id = NEW.opportunity_id;
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER activity_entry_update AFTER UPDATE ON timeline_entries
        BEGIN
            UPDATE opportunities
            SET last_activity_at = ({LATEST_ACTIVITY.format(deal="NEW.opportunity_id")})
            WHERE id = NEW.opportunity_id;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER activity_note_insert AFTER INSERT ON notes
        WHEN NEW.deleted_at IS NULL
        BEGIN
            UPDATE opportunities
            SET last_activity_at = MAX(
                COALESCE(last_activity_at, NEW.created_at), NEW.created_at
            )
            WHERE id = (
                SELECT opportunity_id FROM timeline_entries WHERE id = NEW.entry_id
            );
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER activity_note_update AFTER UPDATE ON notes
        BEGIN
            UPDATE opportunities
            SET last_activity_at = ({LATEST_ACTIVITY.format(deal="opportunities.id")})
            WHERE id = (
                SELECT opportunity_id FROM timeline_entries WHERE id = NEW.entry_id
            );
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER activity_comment_insert AFTER INSERT ON comments
        WHEN NEW.deleted_at IS NULL
        BEGIN
            UPDATE opportunities
            SET last_activity_at = MAX(
                COALESCE(last_activity_at, NEW.created_at), NEW.created_at
            )
            WHERE id = ({NOTE_DEAL.format(note="NEW.note_id")});
        END
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER activity_comment_update AFTER UPDATE ON comments
        BEGIN
            UPDATE opportunities
            SET last_activity_at = ({LATEST_ACTIVITY.format(deal="opportunities.id")})
            WHERE id = ({NOTE_DEAL.format(note="NEW.note_id")});
        END
        """
    )


def downgrade() -> None:
    for trigger in (
        "activity_entry_insert",
        "activity_entry_update",
        "activity_note_insert",
        "activity_note_update",
        "activity_comment_insert",
        "activity_comment_update",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP INDEX IF EXISTS idx_opportunities_last_activity")
    # SQLite can drop a column since 3.35, and nothing references this one.
    op.execute("ALTER TABLE opportunities DROP COLUMN last_activity_at")
