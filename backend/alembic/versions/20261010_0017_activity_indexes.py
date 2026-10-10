"""Indexes for the dashboard's two scanning aggregations

Milestone 6.2. `docs/FEATURES.md` §10 names one of the six as the expensive
one and says what it needs: "'Activity volume per rep' is the one that scans
the most rows and needs an index on `(created_by, created_at)`."

**The column order here is the other way round, and that is deliberate**
(**D-172**). The query asks "who did what in the last eight weeks", so the
*date* is the selective predicate and the author is what it groups by --
leading with `created_by` makes the date range unusable as a seek, and
`EXPLAIN QUERY PLAN` confirmed the suggested index was never chosen. At §10's
own scale (400 opportunities, ~800,000 activity rows spread over two years)
this is the difference the 300 ms budget turns on. The spec named the pair
correctly and the order wrongly; the measurement is in
`tests/test_dashboard.py::test_each_aggregate_answers_inside_the_budget`.

Three tables, because activity is three things here -- entries, notes and
comments are what `dashboard.activity_per_rep` unions.

**The fourth index is for average time in stage**, which §10 does not mention
and which measurement said needs one just as much: it reads only
`type = 'stage_change'` entries, and without an index that is a scan of every
entry ever written (331 ms at the scale above, against a 300 ms budget). A
*partial* index costs almost nothing here -- a stage change is a handful of
rows per deal, not a row per activity -- and it covers both the filter and
the window function's ordering.

No expression indexes for custom fields: see milestone 6.1. A per-field index
is a migration per field, which is the user-triggered DDL ADR 0006 rejected.
An index on a fixed column pair is a different thing -- it is the shape of a
query this application ships.

Revision ID: 0017_activity_indexes
Revises: 0016_custom_fields
Create Date: 2026-10-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_activity_indexes"
down_revision: str | None = "0016_custom_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("timeline_entries", "notes", "comments")


def upgrade() -> None:
    for table in TABLES:
        op.execute(
            f"""
            CREATE INDEX idx_{table}_created_author
            ON {table} (created_at, created_by)
            """
        )
    op.execute(
        """
        CREATE INDEX idx_timeline_entries_stage_changes
        ON timeline_entries (opportunity_id, event_timestamp, id)
        WHERE type = 'stage_change'
        """
    )
    # The stalled list takes the latest of any entry, note or comment per
    # deal, which is one pass over all three tables with no date floor to
    # narrow it -- there is no cheaper way to ask for a maximum. These three
    # make that pass read index pages rather than table rows: 317 ms to 157 ms
    # at §10's scale, against its 300 ms budget and in line with the 131 ms
    # the spec itself measured.
    op.execute(
        """
        CREATE INDEX idx_timeline_entries_activity
        ON timeline_entries (opportunity_id, event_timestamp)
        """
    )
    op.execute("CREATE INDEX idx_notes_activity ON notes (entry_id, created_at)")
    op.execute("CREATE INDEX idx_comments_activity ON comments (note_id, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_comments_activity")
    op.execute("DROP INDEX IF EXISTS idx_notes_activity")
    op.execute("DROP INDEX IF EXISTS idx_timeline_entries_activity")
    op.execute("DROP INDEX IF EXISTS idx_timeline_entries_stage_changes")
    for table in TABLES:
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_created_author")
