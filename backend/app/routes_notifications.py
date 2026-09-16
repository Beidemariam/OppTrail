import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import get_current_user
from .database import db_connection
from .schemas import NotificationListResponse, NotificationPublic

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def notification_from_row(row: sqlite3.Row) -> NotificationPublic:
    return NotificationPublic(
        id=row["id"],
        type=row["type"],
        payload=json.loads(row["payload"]),
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
