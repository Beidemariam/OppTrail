import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import get_current_user
from .database import db_connection
from .permissions import require_opportunity_access, require_timeline_write
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


router = APIRouter(tags=["timeline"])


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
    return connection.execute(
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


def fetch_note_context(
    connection: sqlite3.Connection,
    note_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
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


def fetch_comment_context(
    connection: sqlite3.Connection,
    comment_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
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
    user: sqlite3.Row = Depends(get_current_user),
) -> TimelineResponse:
    where = [
        "timeline_entries.opportunity_id = ?",
        "timeline_entries.deleted_at IS NULL",
    ]
    params: list[object] = [opportunity_id]

    if q:
        like = f"%{q.strip().lower()}%"
        where.append(
            """
            (
                lower(timeline_entries.title) LIKE ?
                OR lower(timeline_entries.body) LIKE ?
                OR EXISTS (
                    SELECT 1 FROM notes
                    WHERE notes.entry_id = timeline_entries.id
                        AND notes.deleted_at IS NULL
                        AND lower(notes.body) LIKE ?
                )
                OR EXISTS (
                    SELECT 1
                    FROM comments
                    JOIN notes ON notes.id = comments.note_id
                    WHERE notes.entry_id = timeline_entries.id
                        AND notes.deleted_at IS NULL
                        AND comments.deleted_at IS NULL
                        AND lower(comments.body) LIKE ?
                )
            )
            """
        )
        params.extend([like, like, like, like])

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

    with db_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))
        entries = connection.execute(
            f"""
            SELECT timeline_entries.*, users.name AS author_name
            FROM timeline_entries
            LEFT JOIN users ON users.id = timeline_entries.created_by
            WHERE {" AND ".join(where)}
            ORDER BY timeline_entries.event_timestamp ASC, timeline_entries.created_at ASC
            """,
            params,
        ).fetchall()

        entry_ids = [entry["id"] for entry in entries]
        if not entry_ids:
            return TimelineResponse(entries=[])

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
                comments_by_note_id.setdefault(comment["note_id"], []).append(
                    comment_from_row(comment)
                )

        notes_by_entry_id: dict[int, list[NotePublic]] = {}
        for note in notes:
            notes_by_entry_id.setdefault(note["entry_id"], []).append(
                note_from_row(note, comments_by_note_id.get(note["id"], []))
            )

    return TimelineResponse(
        entries=[
            entry_from_row(entry, notes_by_entry_id.get(entry["id"], []))
            for entry in entries
        ]
    )


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
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity_id,
                payload.type,
                payload.title,
                payload.body,
                payload.event_timestamp,
                payload.follow_up_date,
                user["id"],
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT timeline_entries.*, users.name AS author_name
            FROM timeline_entries
            LEFT JOIN users ON users.id = timeline_entries.created_by
            WHERE timeline_entries.id = ?
            """,
            (cursor.lastrowid,),
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
        require_timeline_write(connection, entry["opportunity_id"], int(user["id"]))
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
        require_timeline_write(connection, entry["opportunity_id"], int(user["id"]))
        if entry["system_generated"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System timeline entries cannot be deleted",
            )
        connection.execute(
            """
            UPDATE comments
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE deleted_at IS NULL
                AND note_id IN (
                    SELECT id FROM notes WHERE entry_id = ?
                )
            """,
            (entry_id,),
        )
        connection.execute(
            """
            UPDATE notes
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE entry_id = ? AND deleted_at IS NULL
            """,
            (entry_id,),
        )
        connection.execute(
            "UPDATE timeline_entries SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
            (entry_id,),
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

        cursor = connection.execute(
            """
            INSERT INTO notes (entry_id, body, created_by)
            VALUES (?, ?, ?)
            """,
            (entry_id, payload.body, user["id"]),
        )
        note_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO note_versions (note_id, version_number, body, edited_by)
            VALUES (?, 1, ?, ?)
            """,
            (note_id, payload.body, user["id"]),
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
        require_timeline_write(connection, note["opportunity_id"], int(user["id"]))

        latest_version = connection.execute(
            "SELECT COALESCE(MAX(version_number), 0) AS version_number FROM note_versions WHERE note_id = ?",
            (note_id,),
        ).fetchone()["version_number"]
        next_version = int(latest_version) + 1

        connection.execute(
            """
            UPDATE notes
            SET body = ?, updated_at = CURRENT_TIMESTAMP, edited = 1
            WHERE id = ? AND deleted_at IS NULL
            """,
            (payload.body, note_id),
        )
        connection.execute(
            """
            INSERT INTO note_versions (note_id, version_number, body, edited_by)
            VALUES (?, ?, ?, ?)
            """,
            (note_id, next_version, payload.body, user["id"]),
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


@router.get("/api/notes/{note_id}/versions", response_model=list[NoteVersionPublic])
def list_note_versions(
    note_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> list[NoteVersionPublic]:
    with db_connection() as connection:
        note = fetch_note_context(connection, note_id)
        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note not found",
            )
        require_opportunity_access(connection, note["opportunity_id"], int(user["id"]))
        rows = connection.execute(
            """
            SELECT note_versions.*, users.name AS editor_name
            FROM note_versions
            JOIN users ON users.id = note_versions.edited_by
            WHERE note_versions.note_id = ?
            ORDER BY note_versions.version_number ASC
            """,
            (note_id,),
        ).fetchall()

    return [
        NoteVersionPublic(
            id=row["id"],
            note_id=row["note_id"],
            version_number=row["version_number"],
            body=row["body"],
            edited_by=row["edited_by"],
            editor_name=row["editor_name"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


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
        require_timeline_write(connection, note["opportunity_id"], int(user["id"]))
        connection.execute(
            """
            UPDATE comments
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE note_id = ? AND deleted_at IS NULL
            """,
            (note_id,),
        )
        connection.execute(
            "UPDATE notes SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
            (note_id,),
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
            INSERT INTO comments (note_id, body, created_by)
            VALUES (?, ?, ?)
            """,
            (note_id, payload.body, user["id"]),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT comments.*, users.name AS author_name
            FROM comments
            JOIN users ON users.id = comments.created_by
            WHERE comments.id = ?
            """,
            (cursor.lastrowid,),
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
        role = require_opportunity_access(
            connection,
            comment["opportunity_id"],
            int(user["id"]),
        )
        if role != "owner" and comment["created_by"] != user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the author or owner can delete this comment",
            )

        connection.execute(
            "UPDATE comments SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
            (comment_id,),
        )
        connection.commit()
