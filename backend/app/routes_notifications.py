import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import get_current_user
from .database import db_connection
from .notification_service import parse_notification_payload
from .pagination import Page, PageRequest, cursor_clause, page_params, split_page
from .schemas import NotificationListResponse, NotificationPublic

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
v2_router = APIRouter(prefix="/api/v2", tags=["notifications"])


def notification_from_row(row: sqlite3.Row) -> NotificationPublic:
    return NotificationPublic(
        id=row["id"],
        type=row["type"],
        payload=parse_notification_payload(row["type"], row["payload"]),
        read=bool(row["read"]),
        created_at=row["created_at"],
    )


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    user: sqlite3.Row = Depends(get_current_user),
) -> NotificationListResponse:
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM notifications
            WHERE user_id = ? AND read = 0
            ORDER BY created_at DESC, id DESC
            """,
            (user["id"],),
        ).fetchall()

    return NotificationListResponse(notifications=[notification_from_row(row) for row in rows])


@v2_router.get("/notifications", response_model=Page[NotificationPublic])
def list_notifications_page(
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[NotificationPublic]:
    """The v1 list in the v2 envelope, unread-only exactly as v1 is.

    Read notifications staying visible is the notifications rework (milestone
    1.7, `docs/REVIEW.md` H2), which needs the `read_at`/`grouped_key` columns
    this endpoint does not have yet. Changing the rows it returns here would
    make that milestone's behaviour change invisible — the version boundary
    carries the response *shape*, not the feature.
    """
    continuation, cursor_values = cursor_clause(
        page,
        "created_at",
        "id",
        descending=True,
    )
    params: list[object] = [user["id"], *cursor_values, page.limit + 1]

    with db_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM notifications
            WHERE user_id = ? AND read = 0
            {f"AND {continuation}" if continuation else ""}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["created_at"], row["id"]))
    return Page(items=[notification_from_row(row) for row in rows], next_cursor=next_cursor)


@router.patch("/{notification_id}/read", response_model=NotificationPublic)
def mark_notification_read(
    notification_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> NotificationPublic:
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM notifications WHERE id = ? AND user_id = ?",
            (notification_id, user["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found",
            )

        connection.execute(
            "UPDATE notifications SET read = 1 WHERE id = ? AND user_id = ?",
            (notification_id, user["id"]),
        )
        connection.commit()
        updated = connection.execute(
            "SELECT * FROM notifications WHERE id = ? AND user_id = ?",
            (notification_id, user["id"]),
        ).fetchone()

    return notification_from_row(updated)
