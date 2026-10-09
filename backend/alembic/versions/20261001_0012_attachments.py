"""Attachments on a timeline entry

Milestone 4.3, ADR 0008 and `docs/FEATURES.md` §6. Proposals, quotes and
contracts are the artifacts a deal turns on, and until now they lived in
somebody's inbox instead of on the timeline.

One table, and two of its columns are decisions rather than storage:

- **`sha256` is where the file is**, not a checksum beside a path:
  `uploads.resolve_stored_path` turns it into `{root}/{sha256[:2]}/{sha256}`
  (ADR 0008). Two rows with one digest are two attachments and one file on
  disk, so attaching the same contract to three entries costs one copy. No
  unique index, for that reason -- the digest is deliberately not the row's
  identity.
- **`entry_id` is a foreign key, not ADR 0008's `entity_type`/`entity_id`
  pair** (**D-148**). `docs/ROADMAP.md` is explicit about what an attachment
  hangs off here -- "proposals and contracts attach to the entry they belong
  to" -- and one parent spelled as a key keeps the foreign key, the cascade in
  `soft_delete.py`, and the index this read needs. A second kind of parent is
  an `ALTER TABLE` away if v3's email ingestion needs one.

`deleted_at` because an attachment is content: deleting one is soft, audited
and undoable, like every other thing a person wrote (`soft_delete.py`'s
`USER_DATA_TABLES`). **The file itself is never removed** (**D-149**) -- a
soft-deleted row can come back, and a digest may be shared with a row that was
not deleted, so nothing here unlinks a blob.

There is no version table: an attachment has no editable field. The filename is
what was uploaded and the bytes are what the digest addresses, so invariant 8
has nothing to keep a history of -- unlike a task, where 4.1 shipped editable
fields with no history and 4.2a had to add one.

Revision ID: 0012_attachments
Revises: 0011_task_description_and_versions
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_attachments"
down_revision: str | None = "0011_task_description_and_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES timeline_entries(id),
            sha256 TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            uploaded_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT
        )
        """
    )
    # One entry's attachments, which is the only way they are read: a page of
    # entries asks for the whole set in one query (`entries_with_notes`), in
    # upload order, and every ordering in this app ends in the row id.
    op.execute(
        """
        CREATE INDEX idx_attachments_entry
            ON attachments (entry_id, created_at, id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS attachments")
