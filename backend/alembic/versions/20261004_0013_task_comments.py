"""A discussion on a task

Milestone 4.5, from the human's ruling at the Phase 4 gate ("build both",
overruling **D-146**). A task carries the conversation it provokes -- "chased
them, no answer", "moved to Thursday" -- which until now had to go on the
timeline entry beside it or nowhere.

**Flat and chronological, not threaded** (**D-162**). `comments` was not reused
and not mirrored: a task comment has no timeline entry, so putting it in
`comments` would either break `SearchResultPublic.entry_id` (not nullable, and
a shipped read) or leave task comments silently unsearchable while note
comments are not -- across the seventeen places `comments.note_id` is already
assumed. Mirroring 3.3's threads, replies, resolve and reactions is the
duplication D-146 objected to and is more than was asked for: the request was
"comments on a task as it progresses", which is a log.

So this table carries what a log needs and nothing else. Threading is additive
if it is ever wanted -- the three columns `comments` gained in revision 0007.

`deleted_at` because a comment is content (invariant 7's delete audit, and
`soft_delete.USER_DATA_TABLES`). There is no `updated_at`: a comment is
immutable here exactly as it is on a note (`AGENTS.md` invariant 2), so there
is no edit to record and no version table to add.

Revision ID: 0013_task_comments
Revises: 0012_attachments
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_task_comments"
down_revision: str | None = "0012_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            body TEXT NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT
        )
        """
    )
    # One task's discussion, oldest first, which is the only way these are
    # read -- a page of tasks asks for the whole set in one query, and every
    # ordering in this app ends in the row id.
    op.execute(
        """
        CREATE INDEX idx_task_comments_task
            ON task_comments (task_id, created_at, id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS task_comments")
