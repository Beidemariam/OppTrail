# 0001. Keep SQLite; do not migrate to Postgres

Status: Accepted (v2)

## Context

The brief asks when SQLite must become Postgres. The confirmed target scale answers
it: 20 users, **20 opportunities each (400 total)**, ~200 entries per opportunity.
That is 80,000 entries, 240,000 notes and 480,000 comments — **~800,000 rows in a
~136 MB database**, with 2-3 concurrent writers.

This was seeded and benchmarked rather than estimated. Against the current schema
and query shapes:

| Operation | Measured (p_max) | Budget |
|---|---|---|
| Timeline load, 200 entries + notes + comments | 1.4 ms | 400 ms |
| Dashboard, 400 accessible opportunities | 131 ms | 300 ms |
| Keyword search, worst case (no match, full scan) | 294 ms | 300 ms |

Everything is inside budget on the existing schema, with search the only figure
close to its limit — which ADR 0007 addresses.

## Options

1. **Stay on SQLite.** No migration, no new operational surface.
2. **Migrate to Postgres now.** Real types (`timestamptz`, `jsonb`), concurrent
   writers, mature FTS, but adds a service to run, back up, and connect to.
3. **Stay on SQLite, design for a later swap.** Avoid SQLite-specific features so a
   move is cheap.

## Decision

**Option 1.** Stay on SQLite for v2 and beyond at this scale, and use its
features deliberately rather than avoiding them (FTS5 in ADR 0007, JSON1 in
ADR 0006). Designing around a migration that the numbers do not justify would cost
real capability for a hypothetical.

Enable **WAL mode** and a **busy timeout** at connection setup (`database.py`),
which is the actual concurrency fix at this scale: WAL lets readers proceed during
a write, which is the only contention 2-3 concurrent users will generate.

## Trigger for revisiting

Not user count. The trigger is a **deployment** requirement:

- More than one application instance needs to write (horizontal scaling, or a
  hosting platform with no persistent local disk).
- Sustained write concurrency above ~10 writers.
- The database file exceeds a few GB (currently ~136 MB, so roughly 20x headroom).

None are on the v2 horizon.

## Migration path if the trigger fires

The schema is already portable: no SQLite-specific DDL beyond `AUTOINCREMENT` and
the canonical-timestamp `DEFAULT` expression. With Alembic in place (ADR 0002) the
path is: introduce SQLAlchemy Core for the handful of raw queries that differ,
generate the Postgres schema from the same migration history, `pgloader` the data,
convert `TEXT` timestamps to `timestamptz` (already canonical UTC — a straight cast),
and swap `json_extract` for `jsonb` operators. Estimated at days, not weeks, and
cheaper then than the cost of avoiding SQLite's strengths for years.

## Consequences

- No Postgres to operate, back up, or pay for. Backups stay a single-file snapshot
  (ADR 0011).
- Full-text search and custom fields use SQLite-native features and would need
  rewriting on a swap. Accepted, and scoped to two modules.
- Timestamps stay `TEXT` in the canonical fixed-width UTC format. This invariant is
  load-bearing (see `time_utils.py`) and must survive all v2 schema work.
