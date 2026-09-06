import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from .audit_utils import create_audit_log_entry
from .auth import get_current_user
from .database import db_connection
from .notification_service import create_notification
from .permissions import require_opportunity_owner
from .schemas import (
    AuditLogEntryPublic,
    ShareCreate,
    ShareListResponse,
    SharePublic,
    ShareUpdate,
)
from .timeline_utils import create_system_timeline_entry


router = APIRouter(prefix="/api/opportunities", tags=["sharing"])


def share_from_row(row: sqlite3.Row) -> SharePublic:
    return SharePublic(
        user_id=row["user_id"],
        email=row["email"],
        name=row["name"],
        role=row["role"],
        invited_by=row["invited_by"],
        invited_by_name=row["invited_by_name"],
        created_at=row["created_at"],
    )


def fetch_share_rows(
    connection: sqlite3.Connection,
    opportunity_id: int,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            opportunity_shares.user_id,
            opportunity_shares.role,
            opportunity_shares.invited_by,
            opportunity_shares.created_at,
            shared_user.email,
            shared_user.name,
            inviter.name AS invited_by_name
        FROM opportunity_shares
        JOIN users AS shared_user ON shared_user.id = opportunity_shares.user_id
        JOIN users AS inviter ON inviter.id = opportunity_shares.invited_by
        WHERE opportunity_shares.opportunity_id = ?
            AND opportunity_shares.deleted_at IS NULL
        ORDER BY shared_user.name ASC, shared_user.email ASC
        """,
        (opportunity_id,),
    ).fetchall()


@router.get("/{opportunity_id}/shares", response_model=ShareListResponse)
def list_shares(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> ShareListResponse:
    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        rows = fetch_share_rows(connection, opportunity_id)

    return ShareListResponse(shares=[share_from_row(row) for row in rows])


@router.post(
    "/{opportunity_id}/shares",
    response_model=SharePublic,
    status_code=status.HTTP_201_CREATED,
)
def create_share(
    opportunity_id: int,
    payload: ShareCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> SharePublic:
    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        invited_user = connection.execute(
            "SELECT id, email, name FROM users WHERE email = ?",
            (payload.email,),
        ).fetchone()
        if not invited_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User with that email was not found",
            )

        if invited_user["id"] == user["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Owner cannot be added as a share",
            )

        existing_share = connection.execute(
            """
            SELECT deleted_at
            FROM opportunity_shares
            WHERE opportunity_id = ? AND user_id = ?
            """,
            (opportunity_id, invited_user["id"]),
        ).fetchone()
        if existing_share and existing_share["deleted_at"] is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Opportunity is already shared with that user",
            )

        if existing_share:
            connection.execute(
                """
                UPDATE opportunity_shares
                SET role = ?,
                    invited_by = ?,
                    created_at = CURRENT_TIMESTAMP,
                    deleted_at = NULL
                WHERE opportunity_id = ? AND user_id = ?
                """,
                (payload.role, user["id"], opportunity_id, invited_user["id"]),
            )
        else:
            connection.execute(
                """
                INSERT INTO opportunity_shares (opportunity_id, user_id, role, invited_by)
                VALUES (?, ?, ?, ?)
                """,
                (opportunity_id, invited_user["id"], payload.role, user["id"]),
            )
        create_system_timeline_entry(
            connection=connection,
            opportunity_id=opportunity_id,
            created_by=int(user["id"]),
            entry_type="other",
            title=f"Shared with {invited_user['name']}",
            body=f"{invited_user['name']} was added as {payload.role}.",
        )
        create_audit_log_entry(
            connection=connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="share_added",
            detail={
                "user_id": invited_user["id"],
                "email": invited_user["email"],
                "role": payload.role,
            },
        )
        create_notification(
            connection,
            int(invited_user["id"]),
            "share_added",
            {
                "opportunity_id": opportunity_id,
                "actor_id": int(user["id"]),
                "role": payload.role,
            },
        )
        connection.commit()
        row = next(
            share
            for share in fetch_share_rows(connection, opportunity_id)
            if share["user_id"] == invited_user["id"]
        )

    return share_from_row(row)


@router.patch("/{opportunity_id}/shares/{user_id}", response_model=SharePublic)
def update_share(
    opportunity_id: int,
    user_id: int,
    payload: ShareUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> SharePublic:
    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        share = connection.execute(
            """
            SELECT opportunity_shares.*, users.email, users.name
            FROM opportunity_shares
            JOIN users ON users.id = opportunity_shares.user_id
            WHERE opportunity_shares.opportunity_id = ?
                AND opportunity_shares.user_id = ?
                AND opportunity_shares.deleted_at IS NULL
            """,
            (opportunity_id, user_id),
        ).fetchone()
        if not share:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Share not found",
            )

        if share["role"] != payload.role:
            connection.execute(
                """
                UPDATE opportunity_shares
                SET role = ?
                WHERE opportunity_id = ? AND user_id = ?
                """,
                (payload.role, opportunity_id, user_id),
            )
            create_system_timeline_entry(
                connection=connection,
                opportunity_id=opportunity_id,
                created_by=int(user["id"]),
                entry_type="other",
                title=f"Role changed for {share['name']}",
                body=f"{share['name']} changed from {share['role']} to {payload.role}.",
            )
            create_audit_log_entry(
                connection=connection,
                opportunity_id=opportunity_id,
                actor_id=int(user["id"]),
                action="share_role_changed",
                detail={
                    "user_id": user_id,
                    "email": share["email"],
                    "from_role": share["role"],
                    "to_role": payload.role,
                },
            )
            create_notification(
                connection,
                user_id,
                "share_role_changed",
                {
                    "opportunity_id": opportunity_id,
                    "actor_id": int(user["id"]),
                    "from_role": share["role"],
                    "to_role": payload.role,
                },
            )
            connection.commit()

        rows = fetch_share_rows(connection, opportunity_id)
        row = next(item for item in rows if item["user_id"] == user_id)

    return share_from_row(row)


@router.delete("/{opportunity_id}/shares/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_share(
    opportunity_id: int,
    user_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        share = connection.execute(
            """
            SELECT opportunity_shares.*, users.email, users.name
            FROM opportunity_shares
            JOIN users ON users.id = opportunity_shares.user_id
            WHERE opportunity_shares.opportunity_id = ?
                AND opportunity_shares.user_id = ?
                AND opportunity_shares.deleted_at IS NULL
            """,
            (opportunity_id, user_id),
        ).fetchone()
        if not share:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Share not found",
            )

        connection.execute(
            """
            UPDATE opportunity_shares
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE opportunity_id = ? AND user_id = ? AND deleted_at IS NULL
            """,
            (opportunity_id, user_id),
        )
        create_system_timeline_entry(
            connection=connection,
            opportunity_id=opportunity_id,
            created_by=int(user["id"]),
            entry_type="other",
            title=f"Sharing removed for {share['name']}",
            body=f"{share['name']} no longer has access.",
        )
        create_audit_log_entry(
            connection=connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="share_removed",
            detail={
                "user_id": user_id,
                "email": share["email"],
                "role": share["role"],
            },
        )
        create_notification(
            connection,
            user_id,
            "share_removed",
            {
                "opportunity_id": opportunity_id,
                "actor_id": int(user["id"]),
                "role": share["role"],
            },
        )
        connection.commit()


@router.get(
    "/{opportunity_id}/audit-log",
    response_model=list[AuditLogEntryPublic],
)
def list_audit_log(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> list[AuditLogEntryPublic]:
    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        rows = connection.execute(
            """
            SELECT audit_log_entries.*, users.name AS actor_name
            FROM audit_log_entries
            LEFT JOIN users ON users.id = audit_log_entries.actor_id
            WHERE audit_log_entries.opportunity_id = ?
            ORDER BY audit_log_entries.created_at ASC, audit_log_entries.id ASC
            """,
            (opportunity_id,),
        ).fetchall()

    return [
        AuditLogEntryPublic(
            id=row["id"],
            opportunity_id=row["opportunity_id"],
            actor_id=row["actor_id"],
            actor_name=row["actor_name"],
            action=row["action"],
            detail=row["detail"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
