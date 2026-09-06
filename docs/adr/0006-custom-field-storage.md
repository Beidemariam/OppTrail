# 0006. Custom fields: definition table plus a JSON value column

Status: Accepted (v2)

## Context

v2 wants user-defined fields on opportunities and entries. At the confirmed scale
(400 opportunities, 80,000 entries) this is not a performance question — SQLite
handles either shape comfortably — so the decision is made on schema clarity and
query ergonomics.

## Options

1. **EAV** — `custom_values(entity_id, field_id, value)`. Fully relational and
   indexable, but every view that shows N fields becomes N joins or a pivot, and
   typing is lost or duplicated per type column.
2. **JSON column** — `custom_values JSON` on the entity, plus a
   `custom_field_definitions` table for names, types and validation.
3. **Real columns via migration** — one column per field. Strong typing, but user
   -defined fields would mean user-triggered DDL. Rejected outright.

## Decision

**Option 2.** Definitions live in a proper table so the UI, validation, and filter
builder have typed metadata to work from; values live in one JSON column so
rendering a row needs no joins.

- `custom_field_definitions(id, entity_type, key, label, type, options JSON,
  required, position, archived_at)` where `type` is one of
  `text | number | date | select | multi_select | checkbox | user`.
- `opportunities.custom_values JSON` and `timeline_entries.custom_values JSON`,
  defaulting to `{}`.
- Validation happens in Pydantic against the definition set on write. **The JSON
  column is never trusted on read** — unknown keys are ignored, so archiving a
  field does not require rewriting rows.
- Where a field is filtered or sorted often, add an expression index:
  `CREATE INDEX ... ON opportunities(json_extract(custom_values, '$.region'))`.
  SQLite supports these, and at 20 opportunities most will not need one.

## Consequences

- Filtering uses `json_extract`, which is SQLite-specific and would be rewritten as
  `jsonb` operators on a Postgres move (ADR 0001 accepts this).
- No referential integrity between a `user`-typed field value and `users.id`.
  Accepted; validated on write, tolerated on read.
- Type changes on an existing field need a data migration; the UI should allow
  archiving and creating rather than mutating type.
