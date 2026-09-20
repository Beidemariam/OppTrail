"""Saved views: a named filter + sort + group set for a view over one dataset

Milestone 2.2 (`docs/ROADMAP.md` Phase 2, `docs/FEATURES.md` §1). A saved view
is personal or shared, with at most one default per user per entity
(`docs/FEATURES.md`: "[ASSUMPTION] shared views are editable only by their
creator"). `entity` names which shared filter/sort/group model the row
belongs to -- `opportunities` (the board/list/table/calendar dataset) or
`timeline` (one opportunity's entry order, D-051) -- since the two have
different filter shapes and neither should be able to overwrite the other's
default.

`filters` and `sort` are opaque JSON to the database: they mirror whatever the
client's URL query string held (`lib/viewState.ts`), so a new filter field
never needs a migration of its own. `group_by` is a plain column because
grouping is a single named dimension, not an open-ended set.

The partial unique index enforces "one default per user" at the row level
rather than in application code, the same way `opportunity_shares` enforces
"one role per user per opportunity" with a plain `UNIQUE` -- a concurrent
double-write cannot leave two defaults where the application only checked for
one and then raced itself.

Revision ID: 0004_saved_views
Revises: 0003_notification_history
Create Date: 2026-09-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_saved_views"
down_revision: str | None = "0003_notification_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE saved_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_by INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            entity TEXT NOT NULL CHECK (entity IN ('opportunities', 'timeline')),
            filters TEXT NOT NULL DEFAULT '{}',
            sort TEXT NOT NULL DEFAULT '{}',
            group_by TEXT,
            is_shared INTEGER NOT NULL DEFAULT 0 CHECK (is_shared IN (0, 1)),
            is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT
        )
        """
    )
    op.execute("CREATE INDEX idx_saved_views_created_by ON saved_views(created_by)")
    op.execute(
        """
        CREATE UNIQUE INDEX idx_saved_views_default_per_user
            ON saved_views(created_by, entity)
            WHERE is_default = 1 AND deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_saved_views_default_per_user")
    op.execute("DROP INDEX idx_saved_views_created_by")
    op.execute("DROP TABLE saved_views")
