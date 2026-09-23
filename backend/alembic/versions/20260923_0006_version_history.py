"""Edit history for opportunities and timeline entries

Milestone 2.10 (`docs/ROADMAP.md` Phase 2; `AGENTS.md` invariant 8 and v2 scope
item 15). Notes have kept every revision since the baseline (`note_versions`);
the other two editable things kept none, so an opportunity moving from 485,000
to 250,000 left no record of what it had been or who changed it.

Both tables follow `note_versions`' shape exactly -- one row per state, never
an update, numbered from 1 per parent -- so the three histories are read the
same way (`app/versioning.py` is the one writer). A version row is a snapshot
of every editable field, not a diff: the reader wants "what did it say then",
and a diff is one subtraction away from a snapshot while a snapshot is not
recoverable from a chain of diffs with a gap in it.

Neither snapshot table repeats the live table's CHECK constraints on `stage`
and `type`. A version records what the row said at the time, and a constraint
list that can be extended (revision 0005 extended the entry types) or narrowed
would decide, later, which history is still writable -- the fixed stage list is
a rule about opportunities (`AGENTS.md` invariant 6), enforced where
opportunities are written.

**The backfill's one honest limitation.** Every existing row gets a version 1
holding its current values, attributed to its owner (`opportunities.owner_id`)
or author (`timeline_entries.created_by`) and stamped with its `created_at`.
For a row never edited that is exactly true. For a row edited before this
revision it is the only baseline that exists -- the previous values were
overwritten in place and are gone -- so version 1 reads as "the oldest state
this database can still show" rather than as a recorded edit. Recorded in
DECISIONS.md as D-097.

System-generated entries are skipped: they cannot be edited through the API
(`routes_timeline.update_timeline_entry` answers 403), so a history of one
would always hold exactly the row beside it.

Revision ID: 0006_version_history
Revises: 0005_entry_types
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_version_history"
down_revision: str | None = "0005_entry_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE opportunity_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            version_number INTEGER NOT NULL,
            name TEXT NOT NULL,
            account_name TEXT NOT NULL,
            value NUMERIC NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'USD',
            stage TEXT NOT NULL,
            expected_close_date TEXT,
            edited_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            UNIQUE (opportunity_id, version_number)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE timeline_entry_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES timeline_entries(id),
            version_number INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            event_timestamp TEXT NOT NULL,
            follow_up_date TEXT,
            edited_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            UNIQUE (entry_id, version_number)
        )
        """
    )
    op.execute(
        """
        INSERT INTO opportunity_versions (
            opportunity_id,
            version_number,
            name,
            account_name,
            value,
            currency,
            stage,
            expected_close_date,
            edited_by,
            created_at
        )
        SELECT
            id,
            1,
            name,
            account_name,
            value,
            currency,
            stage,
            expected_close_date,
            owner_id,
            created_at
        FROM opportunities
        """
    )
    op.execute(
        """
        INSERT INTO timeline_entry_versions (
            entry_id,
            version_number,
            type,
            title,
            body,
            event_timestamp,
            follow_up_date,
            edited_by,
            created_at
        )
        SELECT
            id,
            1,
            type,
            title,
            body,
            event_timestamp,
            follow_up_date,
            created_by,
            created_at
        FROM timeline_entries
        WHERE system_generated = 0 AND created_by IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE timeline_entry_versions")
    op.execute("DROP TABLE opportunity_versions")
