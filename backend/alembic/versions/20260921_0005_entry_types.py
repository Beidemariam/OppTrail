"""Three new timeline entry types: site visit, objection, competitor intel

Milestone 2.6 (`docs/ROADMAP.md` Phase 2, `docs/FEATURES.md` §2). Additive, per
the roadmap's own wording ("CHECK extended"): the five other target-list names
(site visit, proposal sent, quote revised, objection, competitor intel,
internal note, task) overlap the shipped eight only in the ones that already
exist (call, email, meeting, stage change) — `demo`, `contract` and `other`
stay, and `task` is deliberately not added here, since Phase 4 gives tasks
their own model (`docs/ROADMAP.md` Phase 4) rather than a timeline entry type.
That leaves three genuinely new concepts: site visit, objection, competitor
intel.

SQLite cannot `ALTER TABLE ... ADD CHECK`, so this is the project's first
table rebuild rather than an additive `ALTER TABLE ADD COLUMN` (contrast
revision 0003). The migration connection (`alembic/env.py`) never turns
`PRAGMA foreign_keys` on, so the rebuild does not need to manage it: SQLite's
default is off, and turning it on mid-transaction is a no-op anyway (it can
only be toggled outside a transaction, which a multi-revision `alembic
upgrade` never is). Row ids are preserved by the copy below, which is what
keeps `notes.entry_id` valid with no data rewritten.

Dropping and recreating the table also drops what SQLite attaches to it by
name: the one index and the three FTS5 triggers from revision 0002. Both are
recreated verbatim below. Nothing in `search_index` itself needs touching —
ids and content are unchanged, only the CHECK constraint is wider.

The copy names every column on both sides rather than using `SELECT *`. A
database bridged from before Alembic existed
(`database.bridge_pre_alembic_database`) added `system_generated` with `ALTER
TABLE ADD COLUMN`, which appends a column rather than inserting it where the
baseline declares it — so that database's physical column order is not the
declared one, and a positional `SELECT *` silently shifts every value after
`created_by` one column over. `tests/test_migrations.py`'s bridged-database
cases are what caught it.

Revision ID: 0005_entry_types
Revises: 0004_saved_views
Create Date: 2026-09-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_entry_types"
down_revision: str | None = "0004_saved_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORIGINAL_TYPES = (
    "'call'",
    "'email'",
    "'meeting'",
    "'demo'",
    "'proposal'",
    "'contract'",
    "'stage_change'",
    "'other'",
)

NEW_TYPES = (
    "'site_visit'",
    "'objection'",
    "'competitor_intel'",
)

COLUMNS = (
    "id, opportunity_id, type, title, body, event_timestamp, follow_up_date, "
    "created_by, system_generated, created_at, deleted_at"
)

INDEX = "CREATE INDEX idx_timeline_entries_opportunity_id ON timeline_entries(opportunity_id)"

TRIGGERS = (
    """
    CREATE TRIGGER timeline_entries_search_insert AFTER INSERT ON timeline_entries BEGIN
        INSERT INTO search_index(rowid, title, body)
        SELECT new.id * 4 + 0, new.title, new.body WHERE new.deleted_at IS NULL;
    END
    """,
    """
    CREATE TRIGGER timeline_entries_search_update AFTER UPDATE ON timeline_entries BEGIN
        INSERT INTO search_index(search_index, rowid, title, body)
        SELECT 'delete', old.id * 4 + 0, old.title, old.body WHERE old.deleted_at IS NULL;
        INSERT INTO search_index(rowid, title, body)
        SELECT new.id * 4 + 0, new.title, new.body WHERE new.deleted_at IS NULL;
    END
    """,
    """
    CREATE TRIGGER timeline_entries_search_delete AFTER DELETE ON timeline_entries BEGIN
        INSERT INTO search_index(search_index, rowid, title, body)
        SELECT 'delete', old.id * 4 + 0, old.title, old.body WHERE old.deleted_at IS NULL;
    END
    """,
)


def _rebuild(allowed_types: tuple[str, ...]) -> None:
    # The new table is built under a scratch name and renamed into place,
    # rather than the live table renamed out of the way: SQLite rewrites
    # every stored reference to a table it renames, `notes.entry_id`'s
    # `REFERENCES timeline_entries(id)` included, so renaming
    # `timeline_entries` itself would point that foreign key at whatever the
    # scratch name was -- permanently, since the rewrite lands in `notes`'
    # own stored SQL and outlives the scratch table being dropped. Nothing
    # yet references the scratch name, so renaming it into place is the
    # direction that touches no other table's definition.
    op.execute(
        f"""
        CREATE TABLE timeline_entries_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            type TEXT NOT NULL CHECK (type IN ({", ".join(allowed_types)})),
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            event_timestamp TEXT NOT NULL,
            follow_up_date TEXT,
            created_by INTEGER REFERENCES users(id),
            system_generated INTEGER NOT NULL DEFAULT 0 CHECK (system_generated IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT
        )
        """
    )
    op.execute(
        f"INSERT INTO timeline_entries_new ({COLUMNS}) SELECT {COLUMNS} FROM timeline_entries"
    )
    op.execute("DROP TABLE timeline_entries")
    op.execute("ALTER TABLE timeline_entries_new RENAME TO timeline_entries")
    op.execute(INDEX)
    for trigger in TRIGGERS:
        op.execute(trigger)


def upgrade() -> None:
    _rebuild(ORIGINAL_TYPES + NEW_TYPES)


def downgrade() -> None:
    _rebuild(ORIGINAL_TYPES)
