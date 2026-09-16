import sqlite3
from typing import Literal

from fastapi import HTTPException, status

Role = Literal["owner", "editor", "viewer"]


def get_opportunity_role(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> Role | None:
    row = connection.execute(
        """
        SELECT opportunities.owner_id, opportunity_shares.role
        FROM opportunities
        LEFT JOIN opportunity_shares
            ON opportunity_shares.opportunity_id = opportunities.id
            AND opportunity_shares.user_id = ?
            AND opportunity_shares.deleted_at IS NULL
        WHERE opportunities.id = ?
            AND opportunities.deleted_at IS NULL
            AND (
                opportunities.owner_id = ?
                OR opportunity_shares.user_id IS NOT NULL
            )
        """,
        (user_id, opportunity_id, user_id),
    ).fetchone()

    if not row:
        return None
    if row["owner_id"] == user_id:
        return "owner"
    role: Role = row["role"]
    return role


def require_opportunity_access(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> Role:
    role = get_opportunity_role(connection, opportunity_id, user_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found",
        )
    return role


def require_timeline_write(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> Role:
    role = require_opportunity_access(connection, opportunity_id, user_id)
    if role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewer cannot edit this opportunity",
        )
    return role


def require_delete_permission(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
    author_id: int | None,
    detail: str,
) -> Role:
    """Deleting is limited to the author of the item or the opportunity owner.

    Editors may add and edit freely, but removing a colleague's record on a
    shared opportunity is reserved to its author and the owner.
    """
    role = require_timeline_write(connection, opportunity_id, user_id)
    if role != "owner" and author_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    return role


def require_opportunity_owner(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> None:
    role = require_opportunity_access(connection, opportunity_id, user_id)
    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can manage this opportunity",
        )
