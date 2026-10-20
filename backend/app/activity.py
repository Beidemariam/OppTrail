"""One activity log per opportunity (milestone 3.0, D-101).

Three mechanisms record what happens to an opportunity and none of them meet:
**system timeline entries** (created, stage changed, sharing changed),
**audit log rows** (deletions and restores, plus the sharing forensics) and
**version rows** (every edit, in the three `*_versions` tables). Each is read
through its own screen, so nobody could answer "who did what when" in one
place. This module is that place -- a read-side merge over data that already
exists, with no schema change behind it.

Four things about it are load bearing:

- **Each row keeps the visibility rule of the source it came from.** System
  entries are visible to anyone with access, because they are already in the
  timeline. Audit rows stay owner-only (`AGENTS.md` invariant 7) and version
  rows stay owner-only (D-096). So an editor's activity log is the events they
  can already read and an owner's is all three. The merge does not invent a
  fourth visibility tier; widening it is a product decision, logged as D-102
  for the human rather than taken here.
- **An event appears once.** Three sources over the same actions would
  otherwise double-report: the audit row for an access change -- sharing, and
  since 3.0a an ownership transfer -- is dropped because the system entry
  beside it says the same thing to every reader (the audit log endpoint still
  holds them in full), and an opportunity edit reaches the feed
  only when it moved a field other than `stage`, because a stage change
  already writes its own system entry. Version 1 is excluded everywhere by
  the join to the preceding version -- it is the creation baseline, not an
  edit (D-097).
- **The id encodes which source a row came from**, `rank * ACTIVITY_STRIDE +
  source row id`, in the spirit of the FTS5 rowid `search.py` packs the same
  way (ADR 0007). Five tables have five independent id spaces; the feed's
  cursor needs one value that is unique and ordered across all of them. The
  rank leads rather than trails because it is also the tie-break: every
  timestamp this app writes is second-resolution (D-067), so events from one
  action share one, and ordering those by rank puts them in the order the
  action performed them -- a thing is recorded, then edited, then deleted.
  Across seconds the timestamp decides and the rank never comes up.
- **Five queries, merged here, rather than one `UNION`.** The branches have
  nothing in common but actor and time, so a union would project them through
  a row of anonymous columns and unpack it again. Each source is asked for
  `limit + 1` rows past the cursor, which is enough for the merged page to be
  exact: a source can contribute at most `limit` of the first `limit` merged
  rows, so nothing that belongs on the page was left behind.
"""

import sqlite3
from typing import Literal

from .audit_utils import parse_audit_detail
from .pagination import PageRequest, cursor_clause, split_page
from .permissions import Role, visible_entries_clause
from .schemas import (
    ActivityAuditEvent,
    ActivityEditEvent,
    ActivityEventPublic,
    ActivitySystemEvent,
)
from .versioning import (
    NOTE_VERSIONS,
    OPPORTUNITY_VERSIONS,
    TASK_VERSIONS,
    TIMELINE_ENTRY_VERSIONS,
    VersionedTable,
)

ActivitySource = Literal[
    "system_entry",
    "audit_log",
    "opportunity_version",
    "timeline_entry_version",
    "note_version",
    # Milestone 4.2a: tasks are editable and therefore versioned (invariant 8),
    # so their edits belong in the one place that answers "who did what when".
    # The human asked for this at the Phase 4 checkpoint and the invariant
    # already required it.
    "task_version",
]

# How far apart the six id spaces are held, and where each one starts. A
# trillion is past any row count SQLite will hold here, so no source can reach
# into the next one's range; `test_activity.py` is what says so rather than
# this comment.
ACTIVITY_STRIDE = 1_000_000_000_000
# Ranked in the order one action performs them, because this doubles as the
# tie-break inside a second: a row is recorded by a system entry, edited into
# a version, and removed through the audit log.
SOURCE_RANKS: dict[ActivitySource, int] = {
    "system_entry": 0,
    "opportunity_version": 1,
    "timeline_entry_version": 2,
    "note_version": 3,
    "task_version": 4,
    # Stays last: the audit half records what was *removed*, which is the final
    # thing any one action does. Its rank moved from 4 to 5 when tasks joined,
    # and nothing persists a rank -- the id is computed per read, so no stored
    # value changed meaning.
    "audit_log": 5,
}

# An access change writes a system entry *and* an audit row: the three
# `share_*` actions, and since milestone 3.0a the ownership transfer as well.
# The system entry is the one every reader with access already sees, so it is
# the one the feed keeps; `GET /api/v2/opportunities/{id}/audit-log` still
# answers with both (D-103, extended by D-105).
ACCESS_ACTIONS = ("share_added", "share_role_changed", "share_removed", "owner_changed")

# A stage change writes its own `stage_change` system entry, so the version
# row that records the same `PATCH` is only an event when it moved something
# else as well.
OPPORTUNITY_SILENT_FIELDS = ("stage",)


def activity_id(source: ActivitySource, source_id: int) -> int:
    """The feed-wide id for one source row."""
    return SOURCE_RANKS[source] * ACTIVITY_STRIDE + source_id


def _id_expression(column: str, source: ActivitySource) -> str:
    """`activity_id` as SQL, so ordering and the cursor use the same value the
    response carries rather than the source table's own id."""
    return f"({SOURCE_RANKS[source] * ACTIVITY_STRIDE} + {column})"


def _changed_clause(spec: VersionedTable, exclude: tuple[str, ...] = ()) -> str:
    """True when this version moved at least one of these fields, null-safely.

    Built from the same `VersionedTable.fields` the snapshot is written from,
    so a new versioned field is reported by the feed without being named a
    second time here. `IS NOT` rather than `<>` because `expected_close_date`
    and `follow_up_date` are nullable and `NULL <> 'x'` is NULL, not true.
    """
    fields = [field for field in spec.fields if field not in exclude]
    return " OR ".join(f"version.{field} IS NOT previous.{field}" for field in fields)


def _changed_fields(spec: VersionedTable, row: sqlite3.Row) -> list[str]:
    """Which fields this version moved, in the order the table declares them.

    Reported as column names; the label a reader sees is the frontend's, which
    already names these fields for the history screen (`lib/domain.ts`).
    """
    return [field for field in spec.fields if row[field] != row[f"previous_{field}"]]


def _version_columns(spec: VersionedTable) -> str:
    return ", ".join(
        f"version.{field}, previous.{field} AS previous_{field}" for field in spec.fields
    )


def _system_entry_events(
    connection: sqlite3.Connection,
    opportunity_id: int,
    page: PageRequest,
) -> list[ActivityEventPublic]:
    continuation, cursor_values = cursor_clause(
        page,
        "timeline_entries.created_at",
        _id_expression("timeline_entries.id", "system_entry"),
        descending=False,
    )
    rows = connection.execute(
        f"""
        SELECT
            timeline_entries.id,
            timeline_entries.created_at,
            timeline_entries.created_by,
            timeline_entries.title,
            timeline_entries.body,
            users.name AS actor_name
        FROM timeline_entries
        LEFT JOIN users ON users.id = timeline_entries.created_by
        WHERE timeline_entries.opportunity_id = ?
            AND timeline_entries.system_generated = 1
            AND timeline_entries.deleted_at IS NULL
            {f"AND {continuation}" if continuation else ""}
        ORDER BY
            timeline_entries.created_at ASC,
            {_id_expression("timeline_entries.id", "system_entry")} ASC
        LIMIT ?
        """,
        [opportunity_id, *cursor_values, page.limit + 1],
    ).fetchall()
    return [
        ActivityEventPublic(
            id=activity_id("system_entry", row["id"]),
            opportunity_id=opportunity_id,
            occurred_at=row["created_at"],
            actor_id=row["created_by"],
            actor_name=row["actor_name"],
            detail=ActivitySystemEvent(
                entry_id=row["id"],
                title=row["title"],
                body=row["body"],
            ),
        )
        for row in rows
    ]


def _audit_events(
    connection: sqlite3.Connection,
    opportunity_id: int,
    page: PageRequest,
) -> list[ActivityEventPublic]:
    continuation, cursor_values = cursor_clause(
        page,
        "audit_log_entries.created_at",
        _id_expression("audit_log_entries.id", "audit_log"),
        descending=False,
    )
    placeholders = ", ".join("?" for _ in ACCESS_ACTIONS)
    rows = connection.execute(
        f"""
        SELECT audit_log_entries.*, users.name AS actor_name
        FROM audit_log_entries
        LEFT JOIN users ON users.id = audit_log_entries.actor_id
        WHERE audit_log_entries.opportunity_id = ?
            AND audit_log_entries.action NOT IN ({placeholders})
            {f"AND {continuation}" if continuation else ""}
        ORDER BY
            audit_log_entries.created_at ASC,
            {_id_expression("audit_log_entries.id", "audit_log")} ASC
        LIMIT ?
        """,
        [opportunity_id, *ACCESS_ACTIONS, *cursor_values, page.limit + 1],
    ).fetchall()
    return [
        ActivityEventPublic(
            id=activity_id("audit_log", row["id"]),
            opportunity_id=opportunity_id,
            occurred_at=row["created_at"],
            actor_id=row["actor_id"],
            actor_name=row["actor_name"],
            detail=ActivityAuditEvent(
                action=row["action"],
                detail=parse_audit_detail(row["action"], row["detail"]),
            ),
        )
        for row in rows
    ]


def _edit_events(
    connection: sqlite3.Connection,
    opportunity_id: int,
    page: PageRequest,
    *,
    source: ActivitySource,
    spec: VersionedTable,
    target: Literal["opportunity", "timeline_entry", "note", "task"],
    parent_sql: str,
    silent_fields: tuple[str, ...] = (),
    parent_params: tuple[object, ...] = (),
) -> list[ActivityEventPublic]:
    """One versioned table's edits, as feed rows.

    `parent_sql` is the join from the version table down to the opportunity,
    which is also where `deleted_at IS NULL` is asserted at every level: an
    edit to a note that has since been deleted is not an event a reader can
    still make sense of, and the delete itself is in the audit half. It is
    also where a **sealed** entry is dropped (R.1c), which is why
    `parent_params` exists: the two joins that pass through
    `timeline_entries` take the reader's id, and they bind before the cursor
    because the join is written before the `WHERE` continuation.

    The join to `previous` is what makes this "edits" rather than "versions" --
    version 1 has no predecessor, and it is the creation baseline rather than
    a recorded edit (D-097).
    """
    continuation, cursor_values = cursor_clause(
        page,
        "version.created_at",
        _id_expression("version.id", source),
        descending=False,
    )
    rows = connection.execute(
        f"""
        SELECT
            version.id,
            version.{spec.key_column} AS target_id,
            version.version_number,
            version.created_at,
            version.edited_by,
            users.name AS actor_name,
            {_version_columns(spec)}
        FROM {spec.table} AS version
        JOIN {spec.table} AS previous
            ON previous.{spec.key_column} = version.{spec.key_column}
            AND previous.version_number = version.version_number - 1
        JOIN users ON users.id = version.edited_by
        {parent_sql}
            AND ({_changed_clause(spec, silent_fields)})
            {f"AND {continuation}" if continuation else ""}
        ORDER BY version.created_at ASC, {_id_expression("version.id", source)} ASC
        LIMIT ?
        """,
        [opportunity_id, *parent_params, *cursor_values, page.limit + 1],
    ).fetchall()
    return [
        ActivityEventPublic(
            id=activity_id(source, row["id"]),
            opportunity_id=opportunity_id,
            occurred_at=row["created_at"],
            actor_id=row["edited_by"],
            actor_name=row["actor_name"],
            detail=ActivityEditEvent(
                target=target,
                target_id=row["target_id"],
                version_number=row["version_number"],
                changed_fields=_changed_fields(spec, row),
            ),
        )
        for row in rows
    ]


# The three joins from a version row down to the opportunity it belongs to.
# Each opens the `WHERE`, so `_edit_events` can append to it.
OPPORTUNITY_PARENT_SQL = """
    JOIN opportunities ON opportunities.id = version.opportunity_id
    WHERE opportunities.id = ?
        AND opportunities.deleted_at IS NULL
"""

# The two that pass through `timeline_entries` carry the sealed-entry
# predicate (R.1c, **D-209**), and each therefore takes the reader's id after
# the opportunity. Without it this feed was the last place a sealed entry
# announced itself: the timeline stopped showing the card, and an owner still
# read "Blair edited an entry, changing the title" with its id beside it.
# Nothing here ever showed the *content* -- the version read and the restore
# both resolve through `fetch_entry_context` and 404 -- but the existence, the
# author, the time and the field names are exactly what the human's ruling
# says a colleague must not learn.
TIMELINE_ENTRY_PARENT_SQL = f"""
    JOIN timeline_entries ON timeline_entries.id = version.entry_id
    WHERE timeline_entries.opportunity_id = ?
        AND timeline_entries.deleted_at IS NULL
        AND {visible_entries_clause("timeline_entries")}
"""

NOTE_PARENT_SQL = f"""
    JOIN notes ON notes.id = version.note_id
    JOIN timeline_entries ON timeline_entries.id = notes.entry_id
    WHERE timeline_entries.opportunity_id = ?
        AND notes.deleted_at IS NULL
        AND timeline_entries.deleted_at IS NULL
        AND {visible_entries_clause("timeline_entries")}
"""

# A task hangs off the opportunity directly, so this is the shortest of the four
# joins -- no entry in between, even when the task links to one.
TASK_PARENT_SQL = """
    JOIN tasks ON tasks.id = version.task_id
    WHERE tasks.opportunity_id = ?
        AND tasks.deleted_at IS NULL
"""


def fetch_activity_page(
    connection: sqlite3.Connection,
    opportunity_id: int,
    role: Role,
    page: PageRequest,
    reader_id: int,
) -> tuple[list[ActivityEventPublic], str | None]:
    """The merged feed, oldest first, as `(items, next_cursor)`.

    Oldest first is the audit log's order and the three histories': the log is
    read as the narrative of what happened to the opportunity, so the page
    boundary walks forward in time.

    `reader_id` is not a second permission check -- the version half is still
    owner-only and `role` is what decides that. It is the sealed-entry
    predicate (R.1c): an owner may read every *version row* on their deal and
    still not the one belonging to a colleague's private entry, which is one
    predicate rather than a role, exactly as `permissions.py` has it.
    """
    events = _system_entry_events(connection, opportunity_id, page)
    if role == "owner":
        events += _audit_events(connection, opportunity_id, page)
        events += _edit_events(
            connection,
            opportunity_id,
            page,
            source="opportunity_version",
            spec=OPPORTUNITY_VERSIONS,
            target="opportunity",
            parent_sql=OPPORTUNITY_PARENT_SQL,
            silent_fields=OPPORTUNITY_SILENT_FIELDS,
        )
        events += _edit_events(
            connection,
            opportunity_id,
            page,
            source="timeline_entry_version",
            spec=TIMELINE_ENTRY_VERSIONS,
            target="timeline_entry",
            parent_sql=TIMELINE_ENTRY_PARENT_SQL,
            parent_params=(reader_id,),
        )
        events += _edit_events(
            connection,
            opportunity_id,
            page,
            source="note_version",
            spec=NOTE_VERSIONS,
            target="note",
            parent_sql=NOTE_PARENT_SQL,
            parent_params=(reader_id,),
        )
        events += _edit_events(
            connection,
            opportunity_id,
            page,
            source="task_version",
            spec=TASK_VERSIONS,
            target="task",
            parent_sql=TASK_PARENT_SQL,
        )

    events.sort(key=lambda event: (event.occurred_at, event.id))
    return split_page(events, page.limit, lambda event: (event.occurred_at, event.id))
