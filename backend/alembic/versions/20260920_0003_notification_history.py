"""Notification inbox rework: history and grouping columns

Milestone 1.7 (`docs/ROADMAP.md` Phase 1, `docs/FEATURES.md` §9 minus digests).
The v1 inbox returns unread rows only (`WHERE read = 0`,
`routes_notifications.py`), so marking a notification read makes it
disappear rather than move to a history. That is a client-visible behaviour
change, not just a response-shape one, which is why `docs/ROADMAP.md`'s
breaking-changes table keeps it behind `/api/v2`: v1 keeps reading the old
`read` column exactly as before, v2 reads history off `read_at`.

Two additive columns:

- `read_at` — nullable timestamp, NULL means unread. This becomes the source
  of truth; `notification_service.mark_notification_read` /
  `mark_all_notifications_read` write both `read` and `read_at` together so
  the v1 column stays correct without v1's own code changing.
- `grouped_key` — nullable, unused until Phase 5's digest batching (§9's
  "3 new comments on Acme Expansion, not three emails") groups notifications
  before sending a digest. Added now so that feature is a query change, not
  another migration.

Revision ID: 0003_notification_history
Revises: 0002_search_index
Create Date: 2026-09-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_notification_history"
down_revision: str | None = "0002_search_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE notifications ADD COLUMN read_at TEXT")
    op.execute("ALTER TABLE notifications ADD COLUMN grouped_key TEXT")
    # Backfill: the exact original read time is not recorded, so a row already
    # marked read is stamped with its own created_at -- the closest available
    # fact, and one that keeps "read_at IS NULL means unread" true for every
    # row immediately after this migration runs.
    op.execute("UPDATE notifications SET read_at = created_at WHERE read = 1")


def downgrade() -> None:
    op.execute("ALTER TABLE notifications DROP COLUMN grouped_key")
    op.execute("ALTER TABLE notifications DROP COLUMN read_at")
