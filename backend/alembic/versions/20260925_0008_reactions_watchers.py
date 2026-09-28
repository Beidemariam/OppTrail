"""Reactions on comments, and watchers on an opportunity

Milestone 3.3a (`docs/ROADMAP.md` Phase 3, `docs/FEATURES.md` §7), the other
half of the roadmap's single "threaded comments, reactions, resolve/unresolve,
watchers" line that 3.3 (revision 0007) split off (D-126). Two new tables,
unrelated to each other beyond both being small collaboration signals rather
than content:

- **`reactions`** — one row per (comment, person, emoji). A reaction attaches
  to any comment, thread root or reply alike, since `FEATURES.md` §7 names
  "threaded comments with reactions" as one feature rather than two. The
  unique index makes toggling the same emoji twice a no-op the route expresses
  as `INSERT OR IGNORE` rather than a 409 the UI would have to swallow.
- **`watchers`** — one row per (opportunity, person). `FEATURES.md` §7 is
  explicit that this is "follow an opportunity you are not shared on", so the
  table carries no role and no relationship to `opportunity_shares`: watching
  is orthogonal to access, not a weaker grant of it (D-129).

Neither table is in `app.soft_delete.USER_DATA_TABLES`. Both are toggle state
a person sets and unsets — "I am currently reacting/watching" — not content
whose history is worth keeping, the same reasoning that already excludes
`sessions` (`soft_delete.py`): ephemeral state, not user content. `DELETE FROM
reactions` / `DELETE FROM watchers` are therefore ordinary hard deletes and
`tests/test_soft_delete.py`'s scanner is expected to leave them alone (D-130).

Revision ID: 0008_reactions_watchers
Revises: 0007_comment_threads
Create Date: 2026-09-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_reactions_watchers"
down_revision: str | None = "0007_comment_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id INTEGER NOT NULL REFERENCES comments(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            emoji TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            UNIQUE (comment_id, user_id, emoji)
        )
        """
    )
    # Every read of a comment's reactions is by comment_id; the unique index
    # above already covers that column as its leading key, so no second index
    # is needed for the lookup.

    op.execute(
        """
        CREATE TABLE watchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            UNIQUE (opportunity_id, user_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE watchers")
    op.execute("DROP TABLE reactions")
