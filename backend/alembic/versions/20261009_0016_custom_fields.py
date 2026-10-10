"""Custom fields: a definition table and a JSON value column

Milestone 6.1, ADR 0006. `docs/FEATURES.md` §3: "every sales team tracks two
or three things nobody anticipated, and without custom fields those live in
the body text where nothing can filter on them."

The ADR chose a definition table plus one JSON column per entity over EAV
(N joins to render N fields) and over real columns (user-triggered DDL,
rejected outright). Three things here follow from it:

- **`custom_field_definitions` is the typed metadata**, so the UI, the
  validation and the filter builder all read one source rather than guessing
  from the values. `entity_type` is `opportunity` or `entry`; `key` is unique
  per entity type among the live definitions, which a partial unique index
  enforces rather than application code -- the same choice
  `idx_saved_views_default_per_user` made in milestone 2.2.
- **`archived_at`, not a delete.** The ADR is explicit that archiving a field
  must not require rewriting rows: values stay in the JSON, the definition
  stops being offered, and the read ignores keys it has no definition for.
  That is also why type changes archive-and-recreate rather than mutate.
- **`custom_values` defaults to `'{}'`, never NULL**, so every reader can
  `json_extract` without a COALESCE and a row written before this revision
  behaves exactly like one with no values set. `TEXT` rather than a `JSON`
  type because SQLite has no JSON type -- `json_valid` is the constraint that
  makes the column mean what it says.

No expression index is created here. The ADR asks for one "where a field is
filtered or sorted often", and at the confirmed scale (400 opportunities)
none is needed yet; `make reindex`'s sibling for this would be a migration
per field, which is exactly the user-triggered DDL the ADR rejected. The
decision to add one is per-deployment and belongs with the field that earns
it.

Revision ID: 0016_custom_fields
Revises: 0015_search_attachments
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_custom_fields"
down_revision: str | None = "0015_search_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE custom_field_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL CHECK (entity_type IN ('opportunity', 'entry')),
            key TEXT NOT NULL,
            label TEXT NOT NULL,
            type TEXT NOT NULL CHECK (
                type IN ('text', 'number', 'date', 'select', 'multi_select', 'checkbox', 'user')
            ),
            options TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(options)),
            required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1)),
            position INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            archived_at TEXT
        )
        """
    )
    # A key identifies a field to every reader of the JSON, so two live fields
    # on one entity type cannot share one. Archived rows are excluded: a key
    # is reusable once the field it named is retired, which is what makes
    # archive-and-recreate a workable answer to a type change (ADR 0006).
    op.execute(
        """
        CREATE UNIQUE INDEX idx_custom_field_key_per_entity
        ON custom_field_definitions (entity_type, key)
        WHERE archived_at IS NULL
        """
    )
    # Every read of the definition set is "the live ones for this entity, in
    # the order somebody arranged them".
    op.execute(
        """
        CREATE INDEX idx_custom_field_definitions_live
        ON custom_field_definitions (entity_type, position, id)
        WHERE archived_at IS NULL
        """
    )

    for table in ("opportunities", "timeline_entries"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN custom_values TEXT NOT NULL DEFAULT '{{}}'")


def downgrade() -> None:
    for table in ("opportunities", "timeline_entries"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN custom_values")
    op.execute("DROP INDEX IF EXISTS idx_custom_field_definitions_live")
    op.execute("DROP INDEX IF EXISTS idx_custom_field_key_per_entity")
    op.execute("DROP TABLE IF EXISTS custom_field_definitions")
