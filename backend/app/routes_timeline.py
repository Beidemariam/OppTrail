import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .attachment_utils import attachments_by_entry_id
from .audit_utils import create_audit_log_entry
from .auth import get_current_user
from .custom_fields import custom_values_or_422, live_definitions, visible_values
from .database import db_connection
from .events import publish_timeline_changed
from .notification_service import (
    notify_mentions,
    notify_note_comment,
    notify_shared_activity,
)
from .pagination import Page, PageRequest, cursor_clause, page_params, split_page
from .permissions import (
    require_delete_permission,
    require_edit_permission,
    require_opportunity_access,
    require_opportunity_owner,
    require_timeline_write,
)
from .schemas import (
    AttachmentPublic,
    CommentCreate,
    CommentPublic,
    CommentThread,
    NoteCreate,
    NotePublic,
    NoteUpdate,
    NoteVersionPublic,
    ReactionCreate,
    ReactionEmoji,
    ReactionPublic,
    TimelineEntryCreate,
    TimelineEntryPublic,
    TimelineEntryUpdate,
    TimelineEntryVersionPublic,
)
from .search import MATCHING_ENTRY_IDS_SQL, match_expression
from .soft_delete import (
    restore_comment,
    restore_note,
    restore_timeline_entry,
    soft_delete_comment,
    soft_delete_note,
    soft_delete_timeline_entry,
)
from .time_utils import utc_now
from .timeline_utils import ENTRY_SEQUENCE_SQL
from .versioning import (
    NOTE_VERSIONS,
    TIMELINE_ENTRY_VERSIONS,
    apply_version,
    fetch_version,
    record_version,
    version_is_current,
)

router = APIRouter(prefix="/api/v2", tags=["timeline"])


def comment_from_row(
    row: sqlite3.Row,
    reactions: list[ReactionPublic] | None = None,
) -> CommentPublic:
    return CommentPublic(
        id=row["id"],
        note_id=row["note_id"],
        parent_id=row["parent_id"],
        body=row["body"],
        created_by=row["created_by"],
        author_name=row["author_name"],
        created_at=row["created_at"],
        reactions=reactions if reactions is not None else [],
    )


def thread_from_row(
    row: sqlite3.Row,
    replies: list[CommentPublic],
    reactions: list[ReactionPublic] | None = None,
) -> CommentThread:
    """A thread root, its replies, and who called it finished (milestone 3.3).

    `resolved_by_name` is carried beside the id for the same reason
    `author_name` is: the reader is shown a person, and a second request per
    thread to turn an id into a name is a round trip the page unit already
    rules out.
    """
    return CommentThread(
        id=row["id"],
        note_id=row["note_id"],
        parent_id=row["parent_id"],
        body=row["body"],
        created_by=row["created_by"],
        author_name=row["author_name"],
        created_at=row["created_at"],
        resolved_at=row["resolved_at"],
        resolved_by=row["resolved_by"],
        resolved_by_name=row["resolved_by_name"],
        replies=replies,
        reactions=reactions if reactions is not None else [],
    )


def reaction_from_row(row: sqlite3.Row) -> ReactionPublic:
    return ReactionPublic(
        id=row["id"],
        comment_id=row["comment_id"],
        emoji=row["emoji"],
        user_id=row["user_id"],
        user_name=row["user_name"],
        created_at=row["created_at"],
    )


def reactions_by_comment_id(
    connection: sqlite3.Connection,
    comment_ids: list[int],
) -> dict[int, list[ReactionPublic]]:
    """Every reaction on the given comments, one query for the whole set
    (milestone 3.3a) -- the same shape `entries_with_notes` already uses for
    notes and comments, so attaching reactions to a page of entries costs one
    more query rather than one per comment.
    """
    if not comment_ids:
        return {}
    placeholders = ",".join("?" for _ in comment_ids)
    rows = connection.execute(
        f"""
        SELECT reactions.*, users.name AS user_name
        FROM reactions
        JOIN users ON users.id = reactions.user_id
        WHERE reactions.comment_id IN ({placeholders})
        ORDER BY reactions.created_at ASC, reactions.id ASC
        """,
        comment_ids,
    ).fetchall()
    grouped: dict[int, list[ReactionPublic]] = {}
    for row in rows:
        grouped.setdefault(row["comment_id"], []).append(reaction_from_row(row))
    return grouped


def threads_from_rows(
    rows: list[sqlite3.Row],
    reactions: dict[int, list[ReactionPublic]] | None = None,
) -> list[CommentThread]:
    """Group one note's comments into threads, roots in the order read.

    The rows arrive flat and chronological, and a reply always exists after
    the root it answers (its parent had to be there to be named), so one pass
    in that order fills every thread before it is used. `reactions` is looked
    up by the caller rather than here, so a page of many notes still costs one
    reactions query rather than one per note.
    """
    reactions = reactions or {}
    threads: dict[int, list[CommentPublic]] = {
        row["id"]: [] for row in rows if row["parent_id"] is None
    }
    for row in rows:
        parent_id = row["parent_id"]
        if parent_id is not None and parent_id in threads:
            threads[parent_id].append(comment_from_row(row, reactions.get(row["id"])))
    return [
        thread_from_row(row, threads[row["id"]], reactions.get(row["id"]))
        for row in rows
        if row["parent_id"] is None
    ]


# Every read of a comment carries the two names it is displayed with: its
# author's, and — for a resolved thread — the name of whoever resolved it.
COMMENT_ROWS_SQL = """
    SELECT
        comments.*,
        users.name AS author_name,
        resolvers.name AS resolved_by_name
    FROM comments
    JOIN users ON users.id = comments.created_by
    LEFT JOIN users AS resolvers ON resolvers.id = comments.resolved_by
"""


def note_from_row(row: sqlite3.Row, comments: list[CommentThread]) -> NotePublic:
    return NotePublic(
        id=row["id"],
        entry_id=row["entry_id"],
        body=row["body"],
        created_by=row["created_by"],
        author_name=row["author_name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        edited=bool(row["edited"]),
        comments=comments,
    )


# The four reads that answer with an entry (the list, and the three writes that
# return the row they touched). Shared for the reason `SHARE_ROWS_SQL` is: the
# `sequence` column has to be on every one of them, since a client cannot tell
# which route produced the entry it is drawing.
ENTRY_ROWS_SQL = f"""
    SELECT
        timeline_entries.*,
        users.name AS author_name,
        {ENTRY_SEQUENCE_SQL} AS sequence
    FROM timeline_entries
    LEFT JOIN users ON users.id = timeline_entries.created_by
"""


def entry_from_row(
    row: sqlite3.Row,
    notes: list[NotePublic],
    attachments: list[AttachmentPublic],
    definitions: list[dict[str, Any]] | None = None,
) -> TimelineEntryPublic:
    """`definitions` is the live custom field set for entries (milestone 6.1),
    read once per request like `notes` and `attachments` are read once per
    page. `None` answers an empty value set.
    """
    return TimelineEntryPublic(
        id=row["id"],
        opportunity_id=row["opportunity_id"],
        type=row["type"],
        title=row["title"],
        body=row["body"],
        event_timestamp=row["event_timestamp"],
        follow_up_date=row["follow_up_date"],
        created_by=row["created_by"],
        author_name=row["author_name"],
        system_generated=bool(row["system_generated"]),
        created_at=row["created_at"],
        sequence=row["sequence"],
        custom_values=visible_values(row["custom_values"], definitions or []),
        notes=notes,
        attachments=attachments,
    )


def fetch_entry_context(
    connection: sqlite3.Connection,
    entry_id: int,
) -> sqlite3.Row | None:
    row: sqlite3.Row | None = connection.execute(
        """
        SELECT timeline_entries.*
        FROM timeline_entries
        JOIN opportunities ON opportunities.id = timeline_entries.opportunity_id
        WHERE timeline_entries.id = ?
            AND timeline_entries.deleted_at IS NULL
            AND opportunities.deleted_at IS NULL
        """,
        (entry_id,),
    ).fetchone()
    return row


def fetch_note_context(
    connection: sqlite3.Connection,
    note_id: int,
) -> sqlite3.Row | None:
    row: sqlite3.Row | None = connection.execute(
        """
        SELECT notes.*, timeline_entries.opportunity_id
        FROM notes
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        JOIN opportunities ON opportunities.id = timeline_entries.opportunity_id
        WHERE notes.id = ?
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
            AND opportunities.deleted_at IS NULL
        """,
        (note_id,),
    ).fetchone()
    return row


def fetch_comment_context(
    connection: sqlite3.Connection,
    comment_id: int,
) -> sqlite3.Row | None:
    row: sqlite3.Row | None = connection.execute(
        """
        SELECT comments.*, timeline_entries.opportunity_id
        FROM comments
        JOIN notes ON notes.id = comments.note_id
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        JOIN opportunities ON opportunities.id = timeline_entries.opportunity_id
        WHERE comments.id = ?
            AND comments.deleted_at IS NULL
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
            AND opportunities.deleted_at IS NULL
        """,
        (comment_id,),
    ).fetchone()
    return row


def fetch_deleted_entry_context(
    connection: sqlite3.Connection,
    entry_id: int,
) -> sqlite3.Row | None:
    """A deleted entry, for the restore path.

    The mirror image of `fetch_entry_context`: the row itself must be deleted,
    and everything above it must not be. An entry whose opportunity is also
    deleted is not restorable on its own — restoring it would put a row back
    into a record nobody can read — so this answers `None` and the route 404s,
    the same answer an entry that was never deleted gets.
    """
    row: sqlite3.Row | None = connection.execute(
        """
        SELECT timeline_entries.*
        FROM timeline_entries
        JOIN opportunities ON opportunities.id = timeline_entries.opportunity_id
        WHERE timeline_entries.id = ?
            AND timeline_entries.deleted_at IS NOT NULL
            AND opportunities.deleted_at IS NULL
        """,
        (entry_id,),
    ).fetchone()
    return row


def fetch_deleted_note_context(
    connection: sqlite3.Connection,
    note_id: int,
) -> sqlite3.Row | None:
    """A deleted note whose entry and opportunity are both still here."""
    row: sqlite3.Row | None = connection.execute(
        """
        SELECT notes.*, timeline_entries.opportunity_id
        FROM notes
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        JOIN opportunities ON opportunities.id = timeline_entries.opportunity_id
        WHERE notes.id = ?
            AND notes.deleted_at IS NOT NULL
            AND timeline_entries.deleted_at IS NULL
            AND opportunities.deleted_at IS NULL
        """,
        (note_id,),
    ).fetchone()
    return row


def fetch_deleted_comment_context(
    connection: sqlite3.Connection,
    comment_id: int,
) -> sqlite3.Row | None:
    """A deleted comment whose note, entry and opportunity are all still here.

    Since milestone 3.3 the thread root counts as a level of that tree: a
    reply put back under a deleted root would be a comment answering nothing,
    which is the same shape the other restore paths already refuse. Deleting
    a root takes its replies with it, so the ordinary undo restores the whole
    thread and never reaches this case.
    """
    row: sqlite3.Row | None = connection.execute(
        """
        SELECT comments.*, timeline_entries.opportunity_id
        FROM comments
        LEFT JOIN comments AS parent ON parent.id = comments.parent_id
        JOIN notes ON notes.id = comments.note_id
        JOIN timeline_entries ON timeline_entries.id = notes.entry_id
        JOIN opportunities ON opportunities.id = timeline_entries.opportunity_id
        WHERE comments.id = ?
            AND comments.deleted_at IS NOT NULL
            AND (comments.parent_id IS NULL OR parent.deleted_at IS NULL)
            AND notes.deleted_at IS NULL
            AND timeline_entries.deleted_at IS NULL
            AND opportunities.deleted_at IS NULL
        """,
        (comment_id,),
    ).fetchone()
    return row


def timeline_filters(
    opportunity_id: int,
    q: str | None,
    type: str | None,
    from_date: str | None,
    to_date: str | None,
    author_id: int | None,
) -> tuple[list[str], list[object]]:
    """The timeline's filter set.

    A function rather than six clauses inside the route because it is sixty
    lines of `WHERE`; it had a second caller while v1 served the same rows
    unpaginated (D-033) and now has one.
    """
    where = [
        "timeline_entries.opportunity_id = ?",
        "timeline_entries.deleted_at IS NULL",
    ]
    params: list[object] = [opportunity_id]

    if q:
        # Was four `LIKE '%…%'` predicates and two correlated EXISTS
        # subqueries, which could use no index and was slowest exactly when the
        # term was rare (ADR 0007). Same question, asked of the FTS5 index.
        expression = match_expression(q)
        if expression is None:
            # Punctuation only: nothing to look for, so nothing matches —
            # which is what the substring form did with it too.
            where.append("0")
        else:
            where.append(f"timeline_entries.id IN ({MATCHING_ENTRY_IDS_SQL})")
            params.append(expression)

    if type:
        where.append("timeline_entries.type = ?")
        params.append(type)

    if from_date:
        where.append("timeline_entries.event_timestamp >= ?")
        params.append(from_date)

    if to_date:
        where.append("timeline_entries.event_timestamp <= ?")
        params.append(to_date)

    if author_id is not None:
        where.append(
            """
            (
                timeline_entries.created_by = ?
                OR EXISTS (
                    SELECT 1 FROM notes
                    WHERE notes.entry_id = timeline_entries.id
                        AND notes.deleted_at IS NULL
                        AND notes.created_by = ?
                )
                OR EXISTS (
                    SELECT 1
                    FROM comments
                    JOIN notes ON notes.id = comments.note_id
                    WHERE notes.entry_id = timeline_entries.id
                        AND notes.deleted_at IS NULL
                        AND comments.deleted_at IS NULL
                        AND comments.created_by = ?
                )
            )
            """
        )
        params.extend([author_id, author_id, author_id])

    return where, params


def entries_with_notes(
    connection: sqlite3.Connection,
    entries: list[sqlite3.Row],
) -> list[TimelineEntryPublic]:
    """Attach every entry's notes, each note's comments, each comment's
    reactions (milestone 3.3a) and each entry's files (milestone 4.3).

    Five queries for the whole set rather than four per entry, so a page of
    entries costs the same number of round trips as one.
    """
    entry_ids = [entry["id"] for entry in entries]
    if not entry_ids:
        return []

    placeholders = ",".join("?" for _ in entry_ids)
    notes = connection.execute(
        f"""
        SELECT notes.*, users.name AS author_name
        FROM notes
        JOIN users ON users.id = notes.created_by
        WHERE notes.deleted_at IS NULL
            AND notes.entry_id IN ({placeholders})
        ORDER BY notes.created_at ASC, notes.id ASC
        """,
        entry_ids,
    ).fetchall()

    note_ids = [note["id"] for note in notes]
    comments_by_note_id: dict[int, list[CommentThread]] = {}
    if note_ids:
        note_placeholders = ",".join("?" for _ in note_ids)
        comments = connection.execute(
            f"""
            {COMMENT_ROWS_SQL}
            WHERE comments.deleted_at IS NULL
                AND comments.note_id IN ({note_placeholders})
            ORDER BY comments.created_at ASC, comments.id ASC
            """,
            note_ids,
        ).fetchall()
        reactions = reactions_by_comment_id(connection, [comment["id"] for comment in comments])
        rows_by_note_id: dict[int, list[sqlite3.Row]] = {}
        for comment in comments:
            rows_by_note_id.setdefault(comment["note_id"], []).append(comment)
        comments_by_note_id = {
            note_id: threads_from_rows(rows, reactions) for note_id, rows in rows_by_note_id.items()
        }

    notes_by_entry_id: dict[int, list[NotePublic]] = {}
    for note in notes:
        notes_by_entry_id.setdefault(note["entry_id"], []).append(
            note_from_row(note, comments_by_note_id.get(note["id"], []))
        )

    attachments_by_entry = attachments_by_entry_id(connection, entry_ids)
    definitions = live_definitions(connection, "entry")

    return [
        entry_from_row(
            entry,
            notes_by_entry_id.get(entry["id"], []),
            attachments_by_entry.get(entry["id"], []),
            definitions,
        )
        for entry in entries
    ]


@router.get(
    "/opportunities/{opportunity_id}/timeline",
    response_model=Page[TimelineEntryPublic],
)
def list_timeline_page(
    opportunity_id: int,
    page: PageRequest = Depends(page_params),
    q: str | None = None,
    type: str | None = None,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    author_id: int | None = None,
    order: Literal["asc", "desc"] = "asc",
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[TimelineEntryPublic]:
    """The page unit is the entry. Its notes and comments come with it whole —
    an entry split across two pages would be a worse shape than a long one,
    and `docs/ROADMAP.md` puts threaded comments in Phase 3, which is where a
    nested page would belong if one is ever needed.

    Equal `event_timestamp`s tie-break on the entry id rather than on
    `created_at`: a cursor needs a column that is unique within the ordering,
    and for rows created in sequence the two order identically.

    `order` (D-051) reverses both the `ORDER BY` and the cursor's comparison
    direction (`cursor_clause`'s `descending`) — reversing only the `ORDER BY`
    would keep walking the cursor forward through what is now a descending
    list and either repeat or skip rows at the page boundary.
    """
    where, params = timeline_filters(opportunity_id, q, type, from_date, to_date, author_id)
    descending = order == "desc"
    continuation, cursor_values = cursor_clause(
        page,
        "timeline_entries.event_timestamp",
        "timeline_entries.id",
        descending=descending,
    )
    if continuation:
        where.append(continuation)
        params.extend(cursor_values)
    params.append(page.limit + 1)
    direction = "DESC" if descending else "ASC"

    with db_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))
        rows = connection.execute(
            f"""
            {ENTRY_ROWS_SQL}
            WHERE {" AND ".join(where)}
            ORDER BY timeline_entries.event_timestamp {direction}, timeline_entries.id {direction}
            LIMIT ?
            """,
            params,
        ).fetchall()

        entries, next_cursor = split_page(
            rows, page.limit, lambda row: (row["event_timestamp"], row["id"])
        )
        return Page(items=entries_with_notes(connection, entries), next_cursor=next_cursor)


@router.post(
    "/opportunities/{opportunity_id}/timeline",
    response_model=TimelineEntryPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_timeline_entry(
    opportunity_id: int,
    payload: TimelineEntryCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> TimelineEntryPublic:
    created_at = utc_now()
    with db_connection() as connection:
        require_timeline_write(connection, opportunity_id, int(user["id"]))
        cursor = connection.execute(
            """
            INSERT INTO timeline_entries (
                opportunity_id,
                type,
                title,
                body,
                event_timestamp,
                follow_up_date,
                custom_values,
                created_by,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity_id,
                payload.type,
                payload.title,
                payload.body,
                payload.event_timestamp,
                payload.follow_up_date,
                custom_values_or_422(connection, "entry", payload.custom_values),
                user["id"],
                created_at,
            ),
        )
        assert cursor.lastrowid is not None
        entry_id = int(cursor.lastrowid)
        # Version 1 is the entry as written, so a later edit has something to
        # be read against (milestone 2.10). Read back from the row rather than
        # taken from the payload, which is the rule every other version write
        # follows: the snapshot is what the database holds.
        created = connection.execute(
            "SELECT * FROM timeline_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        record_version(
            connection,
            TIMELINE_ENTRY_VERSIONS,
            entry_id,
            created,
            int(user["id"]),
            created_at,
        )
        notify_shared_activity(
            connection,
            opportunity_id,
            int(user["id"]),
            "entry",
            entry_id,
            payload.title,
        )
        connection.commit()
        row = connection.execute(
            f"""
            {ENTRY_ROWS_SQL}
            WHERE timeline_entries.id = ?
            """,
            (entry_id,),
        ).fetchone()
        definitions = live_definitions(connection, "entry")

    publish_timeline_changed(opportunity_id)
    return entry_from_row(row, [], [], definitions)


@router.patch("/timeline/{entry_id}", response_model=TimelineEntryPublic)
def update_timeline_entry(
    entry_id: int,
    payload: TimelineEntryUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> TimelineEntryPublic:
    updates = payload.model_dump(exclude_unset=True)
    # One JSON column, validated against the live definition set rather than
    # assigned like a scalar -- see the same handling in
    # `routes_opportunities.update_opportunity` (milestone 6.1).
    submitted_values = updates.pop("custom_values", None)
    changed = False
    with db_connection() as connection:
        entry = fetch_entry_context(connection, entry_id)
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Timeline entry not found",
            )
        require_edit_permission(
            connection,
            entry["opportunity_id"],
            int(user["id"]),
            entry["created_by"],
            "Only the author or the opportunity owner can edit this timeline entry",
        )
        if entry["system_generated"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System timeline entries cannot be changed",
            )

        if submitted_values is not None:
            updates["custom_values"] = custom_values_or_422(
                connection, "entry", submitted_values, entry["custom_values"]
            )

        if updates:
            assignments = [f"{field} = ?" for field in updates]
            values = [*updates.values(), entry_id]
            connection.execute(
                f"""
                UPDATE timeline_entries
                SET {", ".join(assignments)}
                WHERE id = ? AND deleted_at IS NULL
                """,
                values,
            )
            # Read back rather than assembled from `updates`: a PATCH carries
            # only what changed and a version is the whole state. There is no
            # `updated_at` on this table, so the version carries the write's
            # own clock reading.
            edited = connection.execute(
                "SELECT * FROM timeline_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
            record_version(
                connection,
                TIMELINE_ENTRY_VERSIONS,
                entry_id,
                edited,
                int(user["id"]),
                utc_now(),
            )
            connection.commit()
            changed = True

        row = connection.execute(
            f"""
            {ENTRY_ROWS_SQL}
            WHERE timeline_entries.id = ?
            """,
            (entry_id,),
        ).fetchone()
        definitions = live_definitions(connection, "entry")

    # An empty PATCH wrote nothing, so there is nothing for another reader to
    # go and see: the flag tracks the write rather than the request.
    if changed:
        publish_timeline_changed(entry["opportunity_id"])
    return entry_from_row(row, [], [], definitions)


def timeline_entry_version_from_row(row: sqlite3.Row) -> TimelineEntryVersionPublic:
    return TimelineEntryVersionPublic(
        id=row["id"],
        entry_id=row["entry_id"],
        version_number=row["version_number"],
        type=row["type"],
        title=row["title"],
        body=row["body"],
        event_timestamp=row["event_timestamp"],
        follow_up_date=row["follow_up_date"],
        edited_by=row["edited_by"],
        editor_name=row["editor_name"],
        created_at=row["created_at"],
    )


@router.get("/timeline/{entry_id}/versions", response_model=Page[TimelineEntryVersionPublic])
def list_timeline_entry_versions_page(
    entry_id: int,
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[TimelineEntryVersionPublic]:
    """Oldest version first, owner-only: the three histories answer the same
    question under the same rule (D-096).

    A system-generated entry cannot be edited, so its history is empty rather
    than absent -- the route does not special-case it, because "nothing has
    ever changed here" is the truthful answer and the same one an unedited
    entry gives.
    """
    continuation, cursor_values = cursor_clause(
        page,
        "timeline_entry_versions.version_number",
        "timeline_entry_versions.id",
        descending=False,
    )
    params: list[object] = [entry_id, *cursor_values, page.limit + 1]

    with db_connection() as connection:
        entry = fetch_entry_context(connection, entry_id)
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Timeline entry not found",
            )
        require_opportunity_owner(connection, entry["opportunity_id"], int(user["id"]))
        rows = connection.execute(
            f"""
            SELECT timeline_entry_versions.*, users.name AS editor_name
            FROM timeline_entry_versions
            JOIN users ON users.id = timeline_entry_versions.edited_by
            WHERE timeline_entry_versions.entry_id = ?
            {f"AND {continuation}" if continuation else ""}
            ORDER BY timeline_entry_versions.version_number ASC, timeline_entry_versions.id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["version_number"], row["id"]))
    return Page(
        items=[timeline_entry_version_from_row(row) for row in rows], next_cursor=next_cursor
    )


@router.post(
    "/timeline/{entry_id}/versions/{version_number}/restore",
    response_model=TimelineEntryPublic,
)
def restore_timeline_entry_version(
    entry_id: int,
    version_number: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> TimelineEntryPublic:
    """Put a recorded version of an entry back as the current one (3.1c).

    Owner-only, like the history it restores from (D-096), and distinct from
    `POST /timeline/{id}/restore`, which undoes a soft delete. A system entry
    needs no special case here: it cannot be edited, so it has exactly one
    version, which is always the current one -- and restoring what is already
    current writes nothing (D-120) -- and so announces nothing either.
    """
    changed = False
    with db_connection() as connection:
        entry = fetch_entry_context(connection, entry_id)
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Timeline entry not found",
            )
        require_opportunity_owner(connection, entry["opportunity_id"], int(user["id"]))
        version = fetch_version(connection, TIMELINE_ENTRY_VERSIONS, entry_id, version_number)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Timeline entry version not found",
            )
        current = connection.execute(
            "SELECT * FROM timeline_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()

        if not version_is_current(TIMELINE_ENTRY_VERSIONS, version, current):
            changed = True
            apply_version(connection, TIMELINE_ENTRY_VERSIONS, entry_id, version, {})
            restored = connection.execute(
                "SELECT * FROM timeline_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
            record_version(
                connection,
                TIMELINE_ENTRY_VERSIONS,
                entry_id,
                restored,
                int(user["id"]),
                utc_now(),
            )
            connection.commit()

        row = connection.execute(
            f"""
            {ENTRY_ROWS_SQL}
            WHERE timeline_entries.id = ?
            """,
            (entry_id,),
        ).fetchone()
        definitions = live_definitions(connection, "entry")

    if changed:
        publish_timeline_changed(entry["opportunity_id"])
    return entry_from_row(row, [], [], definitions)


@router.delete("/timeline/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_timeline_entry(
    entry_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        entry = fetch_entry_context(connection, entry_id)
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Timeline entry not found",
            )
        if entry["system_generated"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System timeline entries cannot be deleted",
            )
        require_delete_permission(
            connection,
            entry["opportunity_id"],
            int(user["id"]),
            entry["created_by"],
            "Only the author or owner can delete this timeline entry",
        )
        soft_delete_timeline_entry(connection, entry_id)
        create_audit_log_entry(
            connection=connection,
            opportunity_id=entry["opportunity_id"],
            actor_id=int(user["id"]),
            action="timeline_entry_deleted",
            detail={
                "entry_id": entry_id,
                "type": entry["type"],
                "title": entry["title"],
                "author_id": entry["created_by"],
            },
        )
        connection.commit()
    publish_timeline_changed(entry["opportunity_id"])


# Restore is what makes the undo toast a real `deleted_at = NULL`
# (`docs/FEATURES.md` §12) rather than a re-create under a new id.
@router.post("/timeline/{entry_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_timeline_entry_route(
    entry_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        entry = fetch_deleted_entry_context(connection, entry_id)
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deleted timeline entry not found",
            )
        require_delete_permission(
            connection,
            entry["opportunity_id"],
            int(user["id"]),
            entry["created_by"],
            "Only the author or owner can restore this timeline entry",
        )
        restore_timeline_entry(connection, entry_id, entry["deleted_at"])
        create_audit_log_entry(
            connection=connection,
            opportunity_id=entry["opportunity_id"],
            actor_id=int(user["id"]),
            action="timeline_entry_restored",
            detail={
                "entry_id": entry_id,
                "type": entry["type"],
                "title": entry["title"],
                "author_id": entry["created_by"],
            },
        )
        connection.commit()
    publish_timeline_changed(entry["opportunity_id"])


@router.post(
    "/timeline/{entry_id}/notes",
    response_model=NotePublic,
    status_code=status.HTTP_201_CREATED,
)
def create_note(
    entry_id: int,
    payload: NoteCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> NotePublic:
    with db_connection() as connection:
        entry = fetch_entry_context(connection, entry_id)
        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Timeline entry not found",
            )
        require_timeline_write(connection, entry["opportunity_id"], int(user["id"]))

        created_at = utc_now()
        cursor = connection.execute(
            """
            INSERT INTO notes (entry_id, body, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entry_id, payload.body, user["id"], created_at, created_at),
        )
        assert cursor.lastrowid is not None
        note_id = int(cursor.lastrowid)
        # Read back, like every other version write: the snapshot is the row
        # the database holds, not the request that asked for it.
        written = connection.execute(
            "SELECT * FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        record_version(
            connection,
            NOTE_VERSIONS,
            note_id,
            written,
            int(user["id"]),
            created_at,
        )
        notify_mentions(
            connection,
            entry["opportunity_id"],
            int(user["id"]),
            payload.body,
            "note",
            note_id,
        )
        notify_shared_activity(
            connection,
            entry["opportunity_id"],
            int(user["id"]),
            "note",
            note_id,
            "New note",
        )
        connection.commit()

        row = connection.execute(
            """
            SELECT notes.*, users.name AS author_name
            FROM notes
            JOIN users ON users.id = notes.created_by
            WHERE notes.id = ?
            """,
            (note_id,),
        ).fetchone()

    publish_timeline_changed(entry["opportunity_id"])
    return note_from_row(row, [])


@router.patch("/notes/{note_id}", response_model=NotePublic)
def update_note(
    note_id: int,
    payload: NoteUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> NotePublic:
    """Edit a note, unless somebody else edited it first (ADR 0003).

    The conflict model for the whole app is last-write-wins with *this* guard,
    not CRDTs or operational transforms: comments are immutable and entries
    are rarely co-edited, so a note is the one body two people can be typing
    into at once. `payload.updated_at` is the value the editor was opened
    against; a mismatch means the note moved underneath it and the write is
    refused with 409 rather than silently overwriting what arrived in between.
    Nothing is lost when it does -- `note_versions` holds every recorded state
    and the UI offers to reload.

    Ordered after the permission check, so a viewer is told they may not edit
    rather than that their copy is stale.

    One bounded blind spot, and it is the same second-resolution limit D-067
    already accepted for undo: `utc_now()` has one-second granularity, so two
    edits inside one second carry the same `updated_at` and the later one is
    accepted. That window is where the version history is the recovery
    mechanism rather than the guard.
    """
    with db_connection() as connection:
        note = fetch_note_context(connection, note_id)
        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note not found",
            )
        require_edit_permission(
            connection,
            note["opportunity_id"],
            int(user["id"]),
            note["created_by"],
            "Only the author or the opportunity owner can edit this note",
        )
        if payload.updated_at != note["updated_at"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This note was edited by someone else. Reload it and try again.",
            )

        updated_at = utc_now()
        connection.execute(
            """
            UPDATE notes
            SET body = ?, updated_at = ?, edited = 1
            WHERE id = ? AND deleted_at IS NULL
            """,
            (payload.body, updated_at, note_id),
        )
        # Milestone 2.10 moved the numbering into `versioning.py`, where the
        # opportunity and entry histories now read it too; this is the same
        # insert it always was, written once instead of three times.
        edited = connection.execute(
            "SELECT * FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        record_version(
            connection,
            NOTE_VERSIONS,
            note_id,
            edited,
            int(user["id"]),
            updated_at,
        )
        notify_mentions(
            connection,
            note["opportunity_id"],
            int(user["id"]),
            payload.body,
            "note",
            note_id,
        )
        notify_shared_activity(
            connection,
            note["opportunity_id"],
            int(user["id"]),
            "note",
            note_id,
            "Note updated",
        )
        connection.commit()

        row = connection.execute(
            """
            SELECT notes.*, users.name AS author_name
            FROM notes
            JOIN users ON users.id = notes.created_by
            WHERE notes.id = ?
            """,
            (note_id,),
        ).fetchone()

    publish_timeline_changed(note["opportunity_id"])
    return note_from_row(row, [])


def note_version_from_row(row: sqlite3.Row) -> NoteVersionPublic:
    return NoteVersionPublic(
        id=row["id"],
        note_id=row["note_id"],
        version_number=row["version_number"],
        body=row["body"],
        edited_by=row["edited_by"],
        editor_name=row["editor_name"],
        created_at=row["created_at"],
    )


def require_note_history_access(
    connection: sqlite3.Connection, note_id: int, user_id: int
) -> sqlite3.Row:
    """Owner-only access to a note's history, returning the note it checked --
    the caller needs the row's `opportunity_id` and re-reading it would be a
    second query for what this one already holds.
    """
    note = fetch_note_context(connection, note_id)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )
    require_opportunity_owner(connection, note["opportunity_id"], user_id)
    return note


@router.get("/notes/{note_id}/versions", response_model=Page[NoteVersionPublic])
def list_note_versions_page(
    note_id: int,
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[NoteVersionPublic]:
    """Oldest version first: revision history reads forwards.

    Owner-only since milestone 2.10 (D-096). This route shipped open to every
    role while it was the only history and no screen read it; the milestone
    that gives all three a screen gives them one rule, the audit log's, rather
    than three answers to "who may see what this used to say".
    """
    continuation, cursor_values = cursor_clause(
        page,
        "note_versions.version_number",
        "note_versions.id",
        descending=False,
    )
    params: list[object] = [note_id, *cursor_values, page.limit + 1]

    with db_connection() as connection:
        require_note_history_access(connection, note_id, int(user["id"]))
        rows = connection.execute(
            f"""
            SELECT note_versions.*, users.name AS editor_name
            FROM note_versions
            JOIN users ON users.id = note_versions.edited_by
            WHERE note_versions.note_id = ?
            {f"AND {continuation}" if continuation else ""}
            ORDER BY note_versions.version_number ASC, note_versions.id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["version_number"], row["id"]))
    return Page(items=[note_version_from_row(row) for row in rows], next_cursor=next_cursor)


@router.post(
    "/notes/{note_id}/versions/{version_number}/restore",
    response_model=NotePublic,
)
def restore_note_version(
    note_id: int,
    version_number: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> NotePublic:
    """Put a recorded version of a note back as the current body (3.1c).

    Owner-only through the same check the history read uses, and the same
    write `PATCH /notes/{id}` performs: the body changes, `edited` stays set
    because the note *was* edited, and a version is appended so the text this
    restore replaced is itself recoverable (D-120).

    No mention notification is sent. The body is not new -- whoever it names
    was told when it was first written -- and announcing it a second time
    would make every restore a fresh ping (D-120).
    """
    changed = False
    with db_connection() as connection:
        note = require_note_history_access(connection, note_id, int(user["id"]))
        version = fetch_version(connection, NOTE_VERSIONS, note_id, version_number)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note version not found",
            )
        current = connection.execute(
            "SELECT * FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()

        if not version_is_current(NOTE_VERSIONS, version, current):
            changed = True
            updated_at = utc_now()
            apply_version(
                connection,
                NOTE_VERSIONS,
                note_id,
                version,
                {"updated_at": updated_at, "edited": 1},
            )
            restored = connection.execute(
                "SELECT * FROM notes WHERE id = ?",
                (note_id,),
            ).fetchone()
            record_version(
                connection,
                NOTE_VERSIONS,
                note_id,
                restored,
                int(user["id"]),
                updated_at,
            )
            connection.commit()

        row = connection.execute(
            """
            SELECT notes.*, users.name AS author_name
            FROM notes
            JOIN users ON users.id = notes.created_by
            WHERE notes.id = ?
            """,
            (note_id,),
        ).fetchone()

    if changed:
        publish_timeline_changed(note["opportunity_id"])
    return note_from_row(row, [])


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        note = fetch_note_context(connection, note_id)
        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note not found",
            )
        require_delete_permission(
            connection,
            note["opportunity_id"],
            int(user["id"]),
            note["created_by"],
            "Only the author or owner can delete this note",
        )
        soft_delete_note(connection, note_id)
        create_audit_log_entry(
            connection=connection,
            opportunity_id=note["opportunity_id"],
            actor_id=int(user["id"]),
            action="note_deleted",
            detail={
                "note_id": note_id,
                "entry_id": note["entry_id"],
                "author_id": note["created_by"],
            },
        )
        connection.commit()
    publish_timeline_changed(note["opportunity_id"])


@router.post("/notes/{note_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_note_route(
    note_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        note = fetch_deleted_note_context(connection, note_id)
        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deleted note not found",
            )
        require_delete_permission(
            connection,
            note["opportunity_id"],
            int(user["id"]),
            note["created_by"],
            "Only the author or owner can restore this note",
        )
        restore_note(connection, note_id, note["deleted_at"])
        create_audit_log_entry(
            connection=connection,
            opportunity_id=note["opportunity_id"],
            actor_id=int(user["id"]),
            action="note_restored",
            detail={
                "note_id": note_id,
                "entry_id": note["entry_id"],
                "author_id": note["created_by"],
            },
        )
        connection.commit()
    publish_timeline_changed(note["opportunity_id"])


@router.post(
    "/notes/{note_id}/comments",
    response_model=CommentPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    note_id: int,
    payload: CommentCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> CommentPublic:
    """Open a thread on this note, or reply to one (milestone 3.3).

    `parent_id` must name a live comment on *this* note that is itself a
    thread root. A reply to a reply is refused rather than flattened, because
    silently reparenting it would put an answer under the wrong question
    (D-127); naming a comment on another note is the same request written
    wrong.
    """
    with db_connection() as connection:
        note = fetch_note_context(connection, note_id)
        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note not found",
            )
        require_timeline_write(connection, note["opportunity_id"], int(user["id"]))

        parent: sqlite3.Row | None = None
        if payload.parent_id is not None:
            parent = connection.execute(
                """
                SELECT id, created_by, parent_id
                FROM comments
                WHERE id = ? AND note_id = ? AND deleted_at IS NULL
                """,
                (payload.parent_id, note_id),
            ).fetchone()
            if not parent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Comment not found",
                )
            if parent["parent_id"] is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Replies go under the comment that started the thread",
                )

        cursor = connection.execute(
            """
            INSERT INTO comments (note_id, parent_id, body, created_by, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (note_id, payload.parent_id, payload.body, user["id"], utc_now()),
        )
        assert cursor.lastrowid is not None
        comment_id = int(cursor.lastrowid)
        # Whoever the comment is addressed to: the note's author always, and
        # the author of the comment being answered. One notification each,
        # even when they are the same person.
        recipients = {int(note["created_by"])}
        if parent:
            recipients.add(int(parent["created_by"]))
        notify_note_comment(
            connection,
            recipients,
            int(user["id"]),
            note["opportunity_id"],
            comment_id,
        )
        notify_mentions(
            connection,
            note["opportunity_id"],
            int(user["id"]),
            payload.body,
            "comment",
            comment_id,
        )
        notify_shared_activity(
            connection,
            note["opportunity_id"],
            int(user["id"]),
            "comment",
            comment_id,
            "New comment",
        )
        connection.commit()
        row = connection.execute(
            f"{COMMENT_ROWS_SQL} WHERE comments.id = ?",
            (comment_id,),
        ).fetchone()

    publish_timeline_changed(note["opportunity_id"])
    return comment_from_row(row)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        comment = fetch_comment_context(connection, comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found",
            )
        require_delete_permission(
            connection,
            comment["opportunity_id"],
            int(user["id"]),
            comment["created_by"],
            "Only the author or owner can delete this comment",
        )
        soft_delete_comment(connection, comment_id)
        create_audit_log_entry(
            connection=connection,
            opportunity_id=comment["opportunity_id"],
            actor_id=int(user["id"]),
            action="comment_deleted",
            detail={
                "comment_id": comment_id,
                "note_id": comment["note_id"],
                "author_id": comment["created_by"],
            },
        )
        connection.commit()
    publish_timeline_changed(comment["opportunity_id"])


@router.post("/comments/{comment_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_comment_route(
    comment_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        comment = fetch_deleted_comment_context(connection, comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deleted comment not found",
            )
        require_delete_permission(
            connection,
            comment["opportunity_id"],
            int(user["id"]),
            comment["created_by"],
            "Only the author or owner can restore this comment",
        )
        restore_comment(connection, comment_id, comment["deleted_at"])
        create_audit_log_entry(
            connection=connection,
            opportunity_id=comment["opportunity_id"],
            actor_id=int(user["id"]),
            action="comment_restored",
            detail={
                "comment_id": comment_id,
                "note_id": comment["note_id"],
                "author_id": comment["created_by"],
            },
        )
        connection.commit()
    publish_timeline_changed(comment["opportunity_id"])


def set_thread_resolved(
    comment_id: int,
    user: sqlite3.Row,
    resolved: bool,
) -> CommentThread:
    """Declare a thread finished, or open it again (milestone 3.3).

    The rule is `require_author_or_owner` on the thread's root, the same one
    that decides who may change any existing timeline item (D-005): the
    person who asked can say it is answered, and the opportunity's owner can
    say so about any thread on their deal. Nothing here touches `body` —
    `AGENTS.md` invariant 2 holds, and resolving is a state about a
    discussion rather than an edit of what anyone wrote, which is also why it
    is a POST and not the comment PATCH that must never exist.

    Both directions are idempotent, so a retry of either is safe and the
    first resolver is the one recorded (D-128).
    """
    with db_connection() as connection:
        comment = fetch_comment_context(connection, comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found",
            )
        if comment["parent_id"] is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A reply is resolved with the thread it belongs to",
            )
        require_edit_permission(
            connection,
            comment["opportunity_id"],
            int(user["id"]),
            comment["created_by"],
            "Only the author or owner can resolve this thread",
        )
        if resolved:
            connection.execute(
                """
                UPDATE comments
                SET resolved_at = COALESCE(resolved_at, ?),
                    resolved_by = COALESCE(resolved_by, ?)
                WHERE id = ?
                """,
                (utc_now(), user["id"], comment_id),
            )
        else:
            connection.execute(
                "UPDATE comments SET resolved_at = NULL, resolved_by = NULL WHERE id = ?",
                (comment_id,),
            )
        connection.commit()
        rows = connection.execute(
            f"""
            {COMMENT_ROWS_SQL}
            WHERE comments.deleted_at IS NULL
                AND (comments.id = ? OR comments.parent_id = ?)
            ORDER BY comments.created_at ASC, comments.id ASC
            """,
            (comment_id, comment_id),
        ).fetchall()
        reactions = reactions_by_comment_id(connection, [row["id"] for row in rows])

    publish_timeline_changed(comment["opportunity_id"])
    return threads_from_rows(rows, reactions)[0]


@router.post("/comments/{comment_id}/resolve", response_model=CommentThread)
def resolve_comment(
    comment_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> CommentThread:
    return set_thread_resolved(comment_id, user, resolved=True)


@router.post("/comments/{comment_id}/unresolve", response_model=CommentThread)
def unresolve_comment(
    comment_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> CommentThread:
    return set_thread_resolved(comment_id, user, resolved=False)


@router.post(
    "/comments/{comment_id}/reactions",
    response_model=CommentPublic,
    status_code=status.HTTP_200_OK,
)
def add_reaction(
    comment_id: int,
    payload: ReactionCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> CommentPublic:
    """React to a comment or reply, thread root or answer alike (milestone
    3.3a, D-130).

    Idempotent by construction: `INSERT OR IGNORE` against the
    `(comment_id, user_id, emoji)` unique index means reacting twice with the
    same emoji is the same request repeated, not a second reaction beside the
    first -- which is also why this is 200, not 201 (nothing is guaranteed to
    have been created). Any role that may write the timeline may react; unlike
    editing or deleting, a reaction changes nothing about what anyone wrote,
    so it is not the author-or-owner rule those are.
    """
    with db_connection() as connection:
        comment = fetch_comment_context(connection, comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found",
            )
        require_timeline_write(connection, comment["opportunity_id"], int(user["id"]))
        connection.execute(
            """
            INSERT OR IGNORE INTO reactions (comment_id, user_id, emoji, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (comment_id, user["id"], payload.emoji, utc_now()),
        )
        connection.commit()
        row = connection.execute(
            f"{COMMENT_ROWS_SQL} WHERE comments.id = ?",
            (comment_id,),
        ).fetchone()
        reactions = reactions_by_comment_id(connection, [comment_id]).get(comment_id, [])

    publish_timeline_changed(comment["opportunity_id"])
    return comment_from_row(row, reactions)


@router.delete(
    "/comments/{comment_id}/reactions/{emoji}",
    response_model=CommentPublic,
)
def remove_reaction(
    comment_id: int,
    emoji: ReactionEmoji,
    user: sqlite3.Row = Depends(get_current_user),
) -> CommentPublic:
    """Withdraw the caller's own reaction. Idempotent, like resolve: removing
    a reaction that is not there is not an error (milestone 3.3a).

    Returns the comment with its remaining reactions rather than 204, unlike
    `delete_comment` beside it -- one person's reaction is toggle state on the
    comment, not content being destroyed, and the reader wants the resulting
    count without a second request.
    """
    with db_connection() as connection:
        comment = fetch_comment_context(connection, comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found",
            )
        require_timeline_write(connection, comment["opportunity_id"], int(user["id"]))
        connection.execute(
            "DELETE FROM reactions WHERE comment_id = ? AND user_id = ? AND emoji = ?",
            (comment_id, user["id"], emoji),
        )
        connection.commit()
        row = connection.execute(
            f"{COMMENT_ROWS_SQL} WHERE comments.id = ?",
            (comment_id,),
        ).fetchone()
        reactions = reactions_by_comment_id(connection, [comment_id]).get(comment_id, [])

    publish_timeline_changed(comment["opportunity_id"])
    return comment_from_row(row, reactions)
