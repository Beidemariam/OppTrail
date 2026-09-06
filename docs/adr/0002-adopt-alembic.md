# 0002. Adopt Alembic for schema migrations

Status: Accepted (v2)

## Context

`database.py:34-44` re-runs `schema.sql` (all `CREATE TABLE IF NOT EXISTS`) plus
hand-written additive migrations on **every** startup, guarded by `column_exists()`.
There is no version table, no down path, and no way to express a rename, a type
change, a one-shot backfill, or a rollback.

It also gets slower on every boot: `backfill_opportunity_created_entries` and
`normalize_legacy_timestamps` scan ten columns of every row each time the process
starts.

v2 adds custom fields, attachments, email ingestion, a reworked notification model
and a rich-text format change. Each is a real schema evolution.

## Options

1. Keep the bespoke mechanism and add more guarded blocks.
2. **Alembic.**
3. A minimal hand-rolled `schema_version` table with numbered SQL files.

## Decision

**Option 2, Alembic.** It is the boring, proven choice, it works with SQLite, and
option 3 is a worse Alembic that we would have to maintain.

Note SQLite cannot `ALTER COLUMN`; Alembic's `batch_alter_table` handles this by
rebuilding the table transactionally. That capability is precisely what the current
mechanism lacks.

## Adoption against the existing auto-created schema

1. Introduce Alembic with `sqlalchemy` as a dependency; no ORM adoption implied —
   raw `sqlite3` queries stay.
2. Autogenerate an initial revision from the current `schema.sql` and verify it
   produces a byte-equivalent schema on an empty database.
3. On startup, if `alembic_version` is absent but tables exist, **stamp** the
   baseline revision rather than running it. This is the one-time bridge for the
   existing `data/app.db`.
4. Convert the two existing migrations in `run_migrations()` into revisions; keep
   `normalize_legacy_timestamps` as a **one-shot data migration** that then stops
   running on every boot.
5. Replace `initialize_database()` with `alembic upgrade head` at container start.
6. Delete `schema.sql` and `column_exists()` once the baseline is verified.

## Consequences

- Startup stops doing repeated full-table scans.
- One new dependency (`alembic`, plus `sqlalchemy` as its dependency).
- Migrations become reviewable artifacts with a history, which matters when the
  implementer is an agent working across sessions.
