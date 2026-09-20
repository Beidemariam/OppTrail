import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .audit_utils import create_audit_log_entry
from .auth import get_current_user
from .database import db_connection
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
    require_timeline_write,
)
from .schemas import (
    CommentCreate,
    CommentPublic,
    NoteCreate,
    NotePublic,
    NoteUpdate,
    NoteVersionPublic,
    TimelineEntryCreate,
    TimelineEntryPublic,
    TimelineEntryUpdate,
    TimelineResponse,
)
from .search import MATCHING_ENTRY_IDS_SQL, match_expression
from .soft_delete import (
    soft_delete_comment,
    soft_delete_note,
    soft_delete_timeline_entry,
)
from .time_utils import utc_now

router = APIRouter(tags=["timeline"])
v2_router = APIRouter(prefix="/api/v2", tags=["timeline"])


def comment_from_row(row: sqlite3.Row) -> CommentPublic:
    return CommentPublic(
        id=row["id"],
        note_id=row["note_id"],
        body=row["body"],
        created_by=row["created_by"],
        author_name=row["author_name"],
        created_at=row["created_at"],
    )


def note_from_row(row: sqlite3.Row, comments: list[CommentPublic]) -> NotePublic:
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


def entry_from_row(row: sqlite3.Row, notes: list[NotePublic]) -> TimelineEntryPublic:
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
        notes=notes,
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


def timeline_filters(
    opportunity_id: int,
    q: str | None,
    type: str | None,
    from_date: str | None,
    to_date: str | None,
    author_id: int | None,
) -> tuple[list[str], list[object]]:
    """The timeline's filter set, shared by the v1 and v2 list endpoints so the
    two cannot answer the same question differently.
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
    """Attach every entry's notes and each note's comments.

    Three queries for the whole set rather than two per entry, so a page of
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
    comments_by_note_id: dict[int, list[CommentPublic]] = {}
    if note_ids:
        note_placeholders = ",".join("?" for _ in note_ids)
        comments = connection.execute(
            f"""
            SELECT comments.*, users.name AS author_name
            FROM comments
            JOIN users ON users.id = comments.created_by
            WHERE comments.deleted_at IS NULL
                AND comments.note_id IN ({note_placeholders})
            ORDER BY comments.created_at ASC, comments.id ASC
            """,
            note_ids,
        ).fetchall()
        for comment in comments:
            comments_by_note_id.setdefault(comment["note_id"], []).append(comment_from_row(comment))

    notes_by_entry_id: dict[int, list[NotePublic]] = {}
    for note in notes:
        notes_by_entry_id.setdefault(note["entry_id"], []).append(
            note_from_row(note, comments_by_note_id.get(note["id"], []))
        )

    return [entry_from_row(entry, notes_by_entry_id.get(entry["id"], [])) for entry in entries]


@router.get(
    "/api/opportunities/{opportunity_id}/timeline",
    response_model=TimelineResponse,
)
def list_timeline(
    opportunity_id: int,
    q: str | None = None,
    type: str | None = None,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    author_id: int | None = None,
    order: Literal["asc", "desc"] = "asc",
    user: sqlite3.Row = Depends(get_current_user),
) -> TimelineResponse:
    where, params = timeline_filters(opportunity_id, q, type, from_date, to_date, author_id)
    direction = "DESC" if order == "desc" else "ASC"

    with db_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))
        entries = connection.execute(
            f"""
            SELECT timeline_entries.*, users.name AS author_name
            FROM timeline_entries
            LEFT JOIN users ON users.id = timeline_entries.created_by
            WHERE {" AND ".join(where)}
            ORDER BY timeline_entries.event_timestamp {direction},
                timeline_entries.created_at {direction}
            """,
            params,
        ).fetchall()

        return TimelineResponse(entries=entries_with_notes(connection, entries))


@v2_router.get(
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

    v1 tie-breaks equal `event_timestamp`s on `created_at`, which is not unique
    and so cannot carry a cursor; v2 tie-breaks on the entry id, which orders
    identically for rows created in sequence.

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
            SELECT timeline_entries.*, users.name AS author_name
            FROM timeline_entries
            LEFT JOIN users ON users.id = timeline_entries.created_by
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
    "/api/opportunities/{opportunity_id}/timeline",
    response_model=TimelineEntryPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_timeline_entry(
    opportunity_id: int,
    payload: TimelineEntryCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> TimelineEntryPublic:
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
                created_by,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity_id,
                payload.type,
                payload.title,
                payload.body,
                payload.event_timestamp,
                payload.follow_up_date,
                user["id"],
                utc_now(),
            ),
        )
        assert cursor.lastrowid is not None
        entry_id = int(cursor.lastrowid)
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
            """
            SELECT timeline_entries.*, users.name AS author_name
            FROM timeline_entries
            LEFT JOIN users ON users.id = timeline_entries.created_by
            WHERE timeline_entries.id = ?
            """,
            (entry_id,),
        ).fetchone()

    return entry_from_row(row, [])


@router.patch("/api/timeline/{entry_id}", response_model=TimelineEntryPublic)
def update_timeline_entry(
    entry_id: int,
    payload: TimelineEntryUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> TimelineEntryPublic:
    updates = payload.model_dump(exclude_unset=True)
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
            connection.commit()

        row = connection.execute(
            """
            SELECT timeline_entries.*, users.name AS author_name
            FROM timeline_entries
            LEFT JOIN users ON users.id = timeline_entries.created_by
            WHERE timeline_entries.id = ?
            """,
            (entry_id,),
        ).fetchone()

    return entry_from_row(row, [])


@router.delete("/api/timeline/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@router.post(
    "/api/timeline/{entry_id}/notes",
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
        connection.execute(
            """
            INSERT INTO note_versions (note_id, version_number, body, edited_by, created_at)
            VALUES (?, 1, ?, ?, ?)
            """,
            (note_id, payload.body, user["id"], created_at),
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

    return note_from_row(row, [])


@router.patch("/api/notes/{note_id}", response_model=NotePublic)
def update_note(
    note_id: int,
    payload: NoteUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> NotePublic:
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

        latest_version = connection.execute(
            """
            SELECT COALESCE(MAX(version_number), 0) AS version_number
            FROM note_versions
            WHERE note_id = ?
            """,
            (note_id,),
        ).fetchone()["version_number"]
        next_version = int(latest_version) + 1

        updated_at = utc_now()
        connection.execute(
            """
            UPDATE notes
            SET body = ?, updated_at = ?, edited = 1
            WHERE id = ? AND deleted_at IS NULL
            """,
            (payload.body, updated_at, note_id),
        )
        connection.execute(
            """
            INSERT INTO note_versions (note_id, version_number, body, edited_by, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (note_id, next_version, payload.body, user["id"], updated_at),
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

    return note_from_row(row, [])


NOTE_VERSION_ROWS_SQL = """
    SELECT note_versions.*, users.name AS editor_name
    FROM note_versions
    JOIN users ON users.id = note_versions.edited_by
    WHERE note_versions.note_id = ?
"""


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


def require_note_access(connection: sqlite3.Connection, note_id: int, user_id: int) -> None:
    note = fetch_note_context(connection, note_id)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )
    require_opportunity_access(connection, note["opportunity_id"], user_id)


@router.get("/api/notes/{note_id}/versions", response_model=list[NoteVersionPublic])
def list_note_versions(
    note_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> list[NoteVersionPublic]:
    with db_connection() as connection:
        require_note_access(connection, note_id, int(user["id"]))
        rows = connection.execute(
            f"""
            {NOTE_VERSION_ROWS_SQL}
            ORDER BY note_versions.version_number ASC
            """,
            (note_id,),
        ).fetchall()

    return [note_version_from_row(row) for row in rows]


@v2_router.get("/notes/{note_id}/versions", response_model=Page[NoteVersionPublic])
def list_note_versions_page(
    note_id: int,
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[NoteVersionPublic]:
    """Oldest version first, as v1 has it: revision history reads forwards."""
    continuation, cursor_values = cursor_clause(
        page,
        "note_versions.version_number",
        "note_versions.id",
        descending=False,
    )
    params: list[object] = [note_id, *cursor_values, page.limit + 1]

    with db_connection() as connection:
        require_note_access(connection, note_id, int(user["id"]))
        rows = connection.execute(
            f"""
            {NOTE_VERSION_ROWS_SQL}
            {f"AND {continuation}" if continuation else ""}
            ORDER BY note_versions.version_number ASC, note_versions.id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["version_number"], row["id"]))
    return Page(items=[note_version_from_row(row) for row in rows], next_cursor=next_cursor)


@router.delete("/api/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@router.post(
    "/api/notes/{note_id}/comments",
    response_model=CommentPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    note_id: int,
    payload: CommentCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> CommentPublic:
    with db_connection() as connection:
        note = fetch_note_context(connection, note_id)
        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note not found",
            )
        require_timeline_write(connection, note["opportunity_id"], int(user["id"]))

        cursor = connection.execute(
            """
            INSERT INTO comments (note_id, body, created_by, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (note_id, payload.body, user["id"], utc_now()),
        )
        assert cursor.lastrowid is not None
        comment_id = int(cursor.lastrowid)
        notify_note_comment(
            connection,
            int(note["created_by"]),
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
            """
            SELECT comments.*, users.name AS author_name
            FROM comments
            JOIN users ON users.id = comments.created_by
            WHERE comments.id = ?
            """,
            (comment_id,),
        ).fetchone()

    return comment_from_row(row)


@router.delete("/api/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
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
