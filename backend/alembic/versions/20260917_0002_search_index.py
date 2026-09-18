"""FTS5 search index over entries, notes and comments

ADR 0007. One contentless FTS5 table (`content=''`) plus triggers that keep it
current, including the soft-delete transitions the ADR names as the main
correctness risk.

Contentless is what makes the index cheap: a content-duplicating index measured
+212 MB against +13 MB contentless at the benchmarked scale. The price is that
the index stores no text, so it cannot produce `snippet()` output and cannot be
scanned without a `MATCH` — matches are resolved back to their rows and
snippeted in `app/search.py`.

The rowid *is* the document identity: `source id * 4 + kind code`, with kind
codes 0 entry, 1 note, 2 comment. That bijection is why no mapping table is
needed; `app/search.py` holds the same constants and decodes it back.

A contentless table cannot be updated or deleted from with ordinary SQL, so
every removal below uses FTS5's `'delete'` command, which takes the row's
*previous* column values — available in a trigger as `old.*`.

Revision ID: 0002_search_index
Revises: 0001_baseline
Create Date: 2026-09-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_search_index"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The three population statements are repeated by `app.search.INDEX_SOURCES`,
# which the rebuild command runs. A revision is frozen in time and must not
# import application code that will keep changing, so the SQL is copied rather
# than shared -- and `tests/test_search.py::test_rebuild_reproduces_the_index_
# the_migration_built` fails if the two ever drift.
BACKFILL = (
    """
    INSERT INTO search_index(rowid, title, body)
    SELECT id * 4 + 0, title, body FROM timeline_entries WHERE deleted_at IS NULL
    """,
    """
    INSERT INTO search_index(rowid, title, body)
    SELECT id * 4 + 1, '', body FROM notes WHERE deleted_at IS NULL
    """,
    """
    INSERT INTO search_index(rowid, title, body)
    SELECT id * 4 + 2, '', body FROM comments WHERE deleted_at IS NULL
    """,
)

TRIGGERS = (
    # Entries. The `SELECT ... WHERE` form is how a trigger makes a statement
    # conditional: a row that is soft-deleted has no index row, so nothing is
    # written for it and nothing is deleted for it either.
    """
    CREATE TRIGGER timeline_entries_search_insert AFTER INSERT ON timeline_entries BEGIN
        INSERT INTO search_index(rowid, title, body)
        SELECT new.id * 4 + 0, new.title, new.body WHERE new.deleted_at IS NULL;
    END
    """,
    # One UPDATE trigger covers an edit, a soft delete and a restore: remove
    # the row that was indexed, index the row that is now visible. Either half
    # can be a no-op, and both are when a soft-deleted row is touched again.
    """
    CREATE TRIGGER timeline_entries_search_update AFTER UPDATE ON timeline_entries BEGIN
        INSERT INTO search_index(search_index, rowid, title, body)
        SELECT 'delete', old.id * 4 + 0, old.title, old.body WHERE old.deleted_at IS NULL;
        INSERT INTO search_index(rowid, title, body)
        SELECT new.id * 4 + 0, new.title, new.body WHERE new.deleted_at IS NULL;
    END
    """,
    # Nothing in the application hard-deletes user data (soft_delete.py), but
    # the index must not outlive a row that leaves by any other route.
    """
    CREATE TRIGGER timeline_entries_search_delete AFTER DELETE ON timeline_entries BEGIN
        INSERT INTO search_index(search_index, rowid, title, body)
        SELECT 'delete', old.id * 4 + 0, old.title, old.body WHERE old.deleted_at IS NULL;
    END
    """,
    # Notes and comments carry no title; '' is indexed for both halves of every
    # pair so the `'delete'` command is given exactly what was inserted.
    """
    CREATE TRIGGER notes_search_insert AFTER INSERT ON notes BEGIN
        INSERT INTO search_index(rowid, title, body)
        SELECT new.id * 4 + 1, '', new.body WHERE new.deleted_at IS NULL;
    END
    """,
    """
    CREATE TRIGGER notes_search_update AFTER UPDATE ON notes BEGIN
        INSERT INTO search_index(search_index, rowid, title, body)
        SELECT 'delete', old.id * 4 + 1, '', old.body WHERE old.deleted_at IS NULL;
        INSERT INTO search_index(rowid, title, body)
        SELECT new.id * 4 + 1, '', new.body WHERE new.deleted_at IS NULL;
    END
    """,
    """
    CREATE TRIGGER notes_search_delete AFTER DELETE ON notes BEGIN
        INSERT INTO search_index(search_index, rowid, title, body)
        SELECT 'delete', old.id * 4 + 1, '', old.body WHERE old.deleted_at IS NULL;
    END
    """,
    """
    CREATE TRIGGER comments_search_insert AFTER INSERT ON comments BEGIN
        INSERT INTO search_index(rowid, title, body)
        SELECT new.id * 4 + 2, '', new.body WHERE new.deleted_at IS NULL;
    END
    """,
    """
    CREATE TRIGGER comments_search_update AFTER UPDATE ON comments BEGIN
        INSERT INTO search_index(search_index, rowid, title, body)
        SELECT 'delete', old.id * 4 + 2, '', old.body WHERE old.deleted_at IS NULL;
        INSERT INTO search_index(rowid, title, body)
        SELECT new.id * 4 + 2, '', new.body WHERE new.deleted_at IS NULL;
    END
    """,
    """
    CREATE TRIGGER comments_search_delete AFTER DELETE ON comments BEGIN
        INSERT INTO search_index(search_index, rowid, title, body)
        SELECT 'delete', old.id * 4 + 2, '', old.body WHERE old.deleted_at IS NULL;
    END
    """,
)

TRIGGER_NAMES = (
    "timeline_entries_search_insert",
    "timeline_entries_search_update",
    "timeline_entries_search_delete",
    "notes_search_insert",
    "notes_search_update",
    "notes_search_delete",
    "comments_search_insert",
    "comments_search_update",
    "comments_search_delete",
)


def upgrade() -> None:
    # `porter` stems both the stored token and the query token, so "objections"
    # finds "objection"; `unicode61` is the default word tokenizer underneath
    # it. Changing either requires a reindex (`make reindex`).
    op.execute(
        """
        CREATE VIRTUAL TABLE search_index USING fts5(
            title,
            body,
            content='',
            tokenize='porter unicode61'
        )
        """
    )
    for trigger in TRIGGERS:
        op.execute(trigger)
    # Existing rows are indexed here rather than on first search: an upgrade
    # leaves the index complete, so nothing has to detect an empty one at
    # request time.
    for statement in BACKFILL:
        op.execute(statement)


def downgrade() -> None:
    for name in TRIGGER_NAMES:
        op.execute(f"DROP TRIGGER {name}")
    op.execute("DROP TABLE search_index")
