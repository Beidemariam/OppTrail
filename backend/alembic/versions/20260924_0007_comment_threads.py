"""Threaded comments that can be resolved

Milestone 3.3 (`docs/ROADMAP.md` Phase 3, `docs/FEATURES.md` §7). A note's
comments have been one flat list since the baseline, so a question and its
answer are two rows that only happen to be adjacent, and a discussion that is
over looks exactly like one that is not. Three columns fix both halves:

- `parent_id` — the comment this one replies to. NULL is a thread root. The
  application allows exactly one level (a reply's parent must itself be a
  root, `routes_timeline.create_comment`): the column could express a deeper
  tree, but `FEATURES.md` §7 wants a discussion that stays readable, and at
  this app's scale arbitrary depth is decoration that the UI cannot indent
  honestly. D-127.
- `resolved_at` / `resolved_by` — who declared the thread finished, and when.
  On the root only; a reply's pair is always NULL, which the route enforces
  rather than the schema, because a CHECK over another row is not expressible
  here.

Additive `ALTER TABLE ADD COLUMN`s, like revision 0003 and unlike 0005: no
CHECK constraint changes, so the table is not rebuilt and the three FTS5
triggers attached to it (revision 0002) survive untouched. They also stay
*correct*: resolving writes an UPDATE, whose trigger removes and re-indexes
the same body, and the new columns are not indexed content.

Each column is added with an implicit NULL default, which is what SQLite
requires of a column carrying a `REFERENCES` clause.

`AGENTS.md` invariant 2 is unaffected. `body` remains immutable and there is
still no comment edit route; resolving records a state *about* a thread, not
a change to what anyone wrote.

Revision ID: 0007_comment_threads
Revises: 0006_version_history
Create Date: 2026-09-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_comment_threads"
down_revision: str | None = "0006_version_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE comments ADD COLUMN parent_id INTEGER REFERENCES comments(id)")
    op.execute("ALTER TABLE comments ADD COLUMN resolved_at TEXT")
    op.execute("ALTER TABLE comments ADD COLUMN resolved_by INTEGER REFERENCES users(id)")
    # Every read of a note's comments groups replies under their root, so the
    # lookup is by parent as often as it is by note.
    op.execute("CREATE INDEX idx_comments_parent_id ON comments(parent_id)")


def downgrade() -> None:
    op.execute("DROP INDEX idx_comments_parent_id")
    op.execute("ALTER TABLE comments DROP COLUMN resolved_by")
    op.execute("ALTER TABLE comments DROP COLUMN resolved_at")
    op.execute("ALTER TABLE comments DROP COLUMN parent_id")
