"""An entry can be kept to its author, and a deal can carry private notes

Milestone R.1b, on the human's ruling of 2026-10-14: *"the ability to keep
entries private since as an owner, I might not want to share everything with
whoever I give read or edit rights to the opportunity."* They chose **both**
shapes offered: an entry sealed in place, and a notebook beside the deal.

Two pieces of schema, and the reason each is shaped the way it is:

- **`timeline_entries.visibility`** is `shared` or `private`, CHECK-constrained
  like `type` beside it. A column rather than a join table because the rule is
  one bit with one audience: private means *readable by its author alone*. No
  per-entry audience list, for the reason the automations builder has no
  branches — a thing nobody asked for is a thing that will be wrong.

  **It is `NOT NULL DEFAULT 'shared'`**, which is the right default for rows
  that already exist: nothing in a database written before today was authored
  with privacy in mind, so backfilling them as private would hide history
  people have already read. What a *new* entry defaults to is a decision in
  the API (`schemas.DEFAULT_ENTRY_VISIBILITY`), not here.

  Added with `ALTER TABLE`, not a table rebuild. Revision 0005 rebuilt this
  table to widen a CHECK list, which is the only reason that was necessary;
  adding a column with its own CHECK needs none of that.

- **`private_notes`** is one row per person per opportunity: what that person
  is keeping to themselves about a deal, in Markdown. Its own table rather
  than a flag on `notes`, because a note hangs off an entry and this hangs off
  nothing — it is not part of the deal's history and must never appear in it.
  The unique index is the whole constraint: one notebook each.

  Soft-deleted like everything else (`AGENTS.md` invariant 5), though nothing
  in the UI deletes one — clearing the text empties it, and the row stays.

No index on `visibility`. Every query that reads it already starts from
`opportunity_id`, which `idx_timeline_entries_opportunity_id` serves, and a
deal has tens of entries rather than thousands; an index on a two-value column
behind an existing one buys nothing. `docs/adr/0006` makes the same argument
about expression indexes for custom fields: the index arrives with the query
that earns it.

Revision ID: 0021_entry_visibility
Revises: 0020_job_runs
Create Date: 2026-10-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_entry_visibility"
down_revision: str | None = "0020_job_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE timeline_entries
        ADD COLUMN visibility TEXT NOT NULL DEFAULT 'shared'
            CHECK (visibility IN ('shared', 'private'))
        """
    )
    # Withdrawing a notification is a soft delete like everything else
    # (`AGENTS.md` invariant 5): sealing an entry after the fact takes its
    # title out of other people's inboxes, and the row stays with a stamp on
    # it. The alternative — deleting it outright — would have been the first
    # hard delete of user data in this app, which is a rule worth more than
    # the bytes.
    op.execute("ALTER TABLE notifications ADD COLUMN deleted_at TEXT")
    op.execute(
        """
        CREATE TABLE private_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            body TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            deleted_at TEXT
        )
        """
    )
    # One notebook per person per deal. Partial, so a soft-deleted row does not
    # hold the slot -- the same shape as `idx_saved_views_default_per_user`.
    op.execute(
        """
        CREATE UNIQUE INDEX idx_private_notes_owner
        ON private_notes (opportunity_id, user_id)
        WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE notifications DROP COLUMN deleted_at")
    op.execute("DROP INDEX IF EXISTS idx_private_notes_owner")
    op.execute("DROP TABLE IF EXISTS private_notes")
    op.execute("ALTER TABLE timeline_entries DROP COLUMN visibility")
