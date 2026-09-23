"""Append-only edit history for everything a user can edit (milestone 2.10).

`AGENTS.md` invariant 8 asks that an edit never destroys what it replaced.
Three tables answer it -- `note_versions` since the baseline,
`opportunity_versions` and `timeline_entry_versions` since revision
`20260923_0006_version_history` -- and they are deliberately the same shape:
one row per state of the parent, numbered from 1, holding every editable field
rather than a diff.

That sameness is what this module exists to keep. Each write path used to own
its own `INSERT`, and only notes had one; a fourth editable thing should add a
`VersionedTable` here and call `record_version`, not write a fourth insert.
The read side stays in the routes, where `CLAUDE.md` puts a query that runs in
one place.

Two rules the callers depend on:

- **A version is written after the row it describes**, from the row as the
  database now holds it, so a partial `PATCH` still records the whole state
  rather than only the fields the request carried.
- **The version's `created_at` is the write's own timestamp** -- for an
  opportunity that is the `updated_at` the same statement set, so the row and
  its newest version agree to the second rather than nearly.
"""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class VersionedTable:
    """One history table: where it lives, what it hangs off, what it snapshots.

    `fields` is the editable set, in the order the columns were declared. It is
    also what a reader is shown, so a field that is not here has no history --
    `created_at`, `created_by` and the ids are immutable
    (`AGENTS.md` invariant 5) and cannot need one.
    """

    table: str
    key_column: str
    fields: tuple[str, ...]


NOTE_VERSIONS = VersionedTable("note_versions", "note_id", ("body",))

OPPORTUNITY_VERSIONS = VersionedTable(
    "opportunity_versions",
    "opportunity_id",
    ("name", "account_name", "value", "currency", "stage", "expected_close_date"),
)

TIMELINE_ENTRY_VERSIONS = VersionedTable(
    "timeline_entry_versions",
    "entry_id",
    ("type", "title", "body", "event_timestamp", "follow_up_date"),
)


def record_version(
    connection: sqlite3.Connection,
    spec: VersionedTable,
    key_value: int,
    row: sqlite3.Row,
    edited_by: int,
    created_at: str,
) -> int:
    """Append the state `row` holds as the next version, and return its number.

    `row` is the parent row itself, read back after the write, so the snapshot
    is what the database says rather than what the request asked for -- which
    is also why a partial `PATCH` still records the whole state. The number is
    read out of the table rather than counted by the caller: the
    `UNIQUE (parent, version_number)` index is what makes a gap or a collision
    impossible, and both halves have to agree on the same next value.
    """
    next_number = int(
        connection.execute(
            f"""
            SELECT COALESCE(MAX(version_number), 0) + 1 AS version_number
            FROM {spec.table}
            WHERE {spec.key_column} = ?
            """,
            (key_value,),
        ).fetchone()["version_number"]
    )
    columns = ", ".join(spec.fields)
    placeholders = ", ".join("?" for _ in spec.fields)
    connection.execute(
        f"""
        INSERT INTO {spec.table}
            ({spec.key_column}, version_number, {columns}, edited_by, created_at)
        VALUES (?, ?, {placeholders}, ?, ?)
        """,
        (
            key_value,
            next_number,
            *(row[field] for field in spec.fields),
            edited_by,
            created_at,
        ),
    )
    return next_number
