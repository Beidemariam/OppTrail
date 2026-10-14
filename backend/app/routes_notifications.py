import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import get_current_user
from .database import db_connection
from .notification_service import (
    mark_all_notifications_read,
    mark_notification_read,
    parse_notification_payload,
)
from .pagination import Page, PageRequest, cursor_clause, page_params, split_page
from .schemas import (
    NotificationMarkAllReadResponse,
    NotificationPublic,
)

router = APIRouter(prefix="/api/v2/notifications", tags=["notifications"])


def notification_from_row(row: sqlite3.Row) -> NotificationPublic:
    return NotificationPublic(
        id=row["id"],
        type=row["type"],
        payload=parse_notification_payload(row["type"], row["payload"]),
        read_at=row["read_at"],
        grouped_key=row["grouped_key"],
        created_at=row["created_at"],
    )


@router.get("", response_model=Page[NotificationPublic])
def list_notifications_page(
    page: PageRequest = Depends(page_params),
    type: str | None = None,
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[NotificationPublic]:
    """The inbox (milestone 1.7): full history, not unread-only, with an
    optional filter by notification type.

    v1 answered a narrower question here -- unread only, which meant marking
    one read made it disappear. That surface is gone with the rest of v1;
    `read_at IS NULL` is the same set, and a reader keeps what they have read.
    """
    # `deleted_at IS NULL` since R.1b: sealing an entry withdraws what it told
    # people, and a withdrawn notification is one this read no longer serves.
    where = ["user_id = ?", "deleted_at IS NULL"]
    params: list[object] = [user["id"]]

    if type:
        where.append("type = ?")
        params.append(type)

    continuation, cursor_values = cursor_clause(
        page,
        "created_at",
        "id",
        descending=True,
    )
    if continuation:
        where.append(continuation)
        params.extend(cursor_values)
    params.append(page.limit + 1)

    with db_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM notifications
            WHERE {" AND ".join(where)}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["created_at"], row["id"]))
    return Page(items=[notification_from_row(row) for row in rows], next_cursor=next_cursor)


@router.post("/mark-all-read", response_model=NotificationMarkAllReadResponse)
def mark_all_notifications_read_route(
    user: sqlite3.Row = Depends(get_current_user),
) -> NotificationMarkAllReadResponse:
    with db_connection() as connection:
        marked = mark_all_notifications_read(connection, int(user["id"]))
    return NotificationMarkAllReadResponse(marked=marked)


@router.patch("/{notification_id}/read", response_model=NotificationPublic)
def mark_notification_read_route(
    notification_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> NotificationPublic:
    with db_connection() as connection:
        updated = mark_notification_read(connection, notification_id, int(user["id"]))
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found",
            )

    return notification_from_row(updated)
