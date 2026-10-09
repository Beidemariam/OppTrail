"""Attachment filenames in the search index, and room for what comes next

Milestone 4.8, from the human's "now" on **D-159**. Two changes, and the
second is the one the 1.4 review asked for by name.

**Attachments become the fourth searchable kind.** The filename is indexed as
the document's title, the way a timeline entry's title is; there is no body,
because nothing reads what is inside the file (**D-158** keeps it that way).

**The encoding widens from `* 4` to `* 8`** (**D-167**). `source id * 4 + kind
code` had exactly one code left, and the note recorded at the 1.4 gate said
the first milestone needing a fourth type should widen rather than spend it:
otherwise v3's email ingestion inherits a rowid rewrite at the same moment it
is parsing untrusted mail. Four codes are free after this.

Widening means every rowid in `search_index` changes, which for a
**contentless** FTS5 table is not a rewrite but a rebuild: the table stores no
text, so discarding it and reading the source rows again produces exactly what
was there (ADR 0007's own argument for contentless, spent here for the first
time). The statements below are the same ones `app/search.py` holds as
`INDEX_SOURCES` -- written out because a revision cannot import application
code, and kept honest by
`tests/test_search.py::test_rebuild_reproduces_the_index_the_migration_built`.

Revision ID: 0015_search_attachments
Revises: 0014_task_assignees
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_search_attachments"
down_revision: str | None = "0014_task_assignees"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, kind code, title column, body column). `None` means the kind has no
# such text and `''` is indexed for it -- both halves of every pair, so FTS5's
# `'delete'` command is handed exactly what was inserted. One tuple per
# searchable kind, so the twelve triggers below are generated rather than
# written out: revision 0002 wrote its nine by hand, and this revision is what
# that cost the first time one number had to change in all of them.
KINDS = (
    ("timeline_entries", 0, "title", "body"),
    ("notes", 1, None, "body"),
    ("comments", 2, None, "body"),
    ("attachments", 3, "filename", None),
)
BASE = 8


def column(prefix: str, name: str | None) -> str:
    """`new.title`, or the empty string literal for a kind that has none."""
    return f"{prefix}.{name}" if name else "''"


def upgrade() -> None:
    for table, _code, _title, _body in KINDS:
        for event in ("insert", "update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_search_{event}")

    for table, code, title, body in KINDS:
        new_title, new_body = column("new", title), column("new", body)
        old_title, old_body = column("old", title), column("old", body)
        op.execute(
            f"""
            CREATE TRIGGER {table}_search_insert AFTER INSERT ON {table} BEGIN
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * {BASE} + {code}, {new_title}, {new_body}
                WHERE new.deleted_at IS NULL;
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {table}_search_update AFTER UPDATE ON {table} BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * {BASE} + {code}, {old_title}, {old_body}
                WHERE old.deleted_at IS NULL;
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * {BASE} + {code}, {new_title}, {new_body}
                WHERE new.deleted_at IS NULL;
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {table}_search_delete AFTER DELETE ON {table} BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * {BASE} + {code}, {old_title}, {old_body}
                WHERE old.deleted_at IS NULL;
            END
            """
        )

    # Every rowid moves, so the index is rebuilt rather than updated: a
    # contentless table cannot be UPDATEd, and it holds no text that a rebuild
    # could lose.
    op.execute("INSERT INTO search_index(search_index) VALUES ('delete-all')")
    for table, code, title, body in KINDS:
        op.execute(
            f"""
            INSERT INTO search_index(rowid, title, body)
            SELECT id * {BASE} + {code}, {title or "''"}, {body or "''"}
            FROM {table} WHERE deleted_at IS NULL
            """
        )


def downgrade() -> None:
    for table, _code, _title, _body in KINDS:
        for event in ("insert", "update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_search_{event}")
    op.execute("INSERT INTO search_index(search_index) VALUES ('delete-all')")
    for table, code, title, body in KINDS[:3]:
        new_title, new_body = column("new", title), column("new", body)
        old_title, old_body = column("old", title), column("old", body)
        op.execute(
            f"""
            CREATE TRIGGER {table}_search_insert AFTER INSERT ON {table} BEGIN
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * 4 + {code}, {new_title}, {new_body}
                WHERE new.deleted_at IS NULL;
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {table}_search_update AFTER UPDATE ON {table} BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * 4 + {code}, {old_title}, {old_body}
                WHERE old.deleted_at IS NULL;
                INSERT INTO search_index(rowid, title, body)
                SELECT new.id * 4 + {code}, {new_title}, {new_body}
                WHERE new.deleted_at IS NULL;
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {table}_search_delete AFTER DELETE ON {table} BEGIN
                INSERT INTO search_index(search_index, rowid, title, body)
                SELECT 'delete', old.id * 4 + {code}, {old_title}, {old_body}
                WHERE old.deleted_at IS NULL;
            END
            """
        )
        op.execute(
            f"""
            INSERT INTO search_index(rowid, title, body)
            SELECT id * 4 + {code}, {title or "''"}, {body or "''"}
            FROM {table} WHERE deleted_at IS NULL
            """
        )
