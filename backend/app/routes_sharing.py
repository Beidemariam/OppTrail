import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from .audit_utils import create_audit_log_entry, parse_audit_detail
from .auth import get_current_user
from .database import db_connection
from .notification_service import create_notification
from .pagination import Page, PageRequest, cursor_clause, page_params, split_page
from .permissions import require_opportunity_access, require_opportunity_owner
from .schemas import (
    AuditLogEntryPublic,
    OpportunityMemberPublic,
    ShareCreate,
    SharePublic,
    ShareUpdate,
)
from .share_utils import upsert_share_row
from .soft_delete import soft_delete_share
from .timeline_utils import create_system_timeline_entry

router = APIRouter(prefix="/api/v2/opportunities", tags=["sharing"])


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


SHARE_ROWS_SQL = """
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
"""


def fetch_share_rows(
    connection: sqlite3.Connection,
    opportunity_id: int,
) -> list[sqlite3.Row]:
    return connection.execute(
        f"""
        {SHARE_ROWS_SQL}
        ORDER BY shared_user.name ASC, shared_user.email ASC
        """,
        (opportunity_id,),
    ).fetchall()


MEMBER_ROWS_SQL = """
    SELECT owner.id AS user_id, owner.email, owner.name, 'owner' AS role
    FROM opportunities
    JOIN users AS owner ON owner.id = opportunities.owner_id
    WHERE opportunities.id = ? AND opportunities.deleted_at IS NULL
    UNION ALL
    SELECT shared_user.id AS user_id, shared_user.email, shared_user.name,
           opportunity_shares.role AS role
    FROM opportunity_shares
    JOIN users AS shared_user ON shared_user.id = opportunity_shares.user_id
    WHERE opportunity_shares.opportunity_id = ?
        AND opportunity_shares.deleted_at IS NULL
"""


@router.get("/{opportunity_id}/members", response_model=Page[OpportunityMemberPublic])
def list_members_page(
    opportunity_id: int,
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[OpportunityMemberPublic]:
    """Everyone who can read this opportunity, for the mention autocomplete
    (milestone 3.2, **D-123**).

    Open to every role, unlike the share list beside it: a mention is only
    delivered to someone who already has access, so a composer that cannot see
    that set can only offer to notify nobody -- which is requirement 13's
    discoverability problem restated. What it answers with is the same three
    facts the timeline already prints beside every entry plus the address a
    mention is written with; the grant itself -- who invited whom, and when --
    stays in `GET .../shares`, owner-only.

    The owner is a row here, which is why this is a `UNION ALL` over the
    two places access comes from rather than a read of `opportunity_shares`:
    ownership is implicit in `opportunities.owner_id` and has no share row
    (`permissions.py`).
    """
    continuation, cursor_values = cursor_clause(
        page,
        "members.name",
        "members.user_id",
        descending=False,
    )
    params: list[object] = [opportunity_id, opportunity_id, *cursor_values, page.limit + 1]

    with db_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))
        rows = connection.execute(
            f"""
            SELECT members.user_id, members.email, members.name, members.role
            FROM ({MEMBER_ROWS_SQL}) AS members
            {f"WHERE {continuation}" if continuation else ""}
            ORDER BY members.name ASC, members.user_id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["name"], row["user_id"]))
    return Page(
        items=[
            OpportunityMemberPublic(
                user_id=row["user_id"],
                email=row["email"],
                name=row["name"],
                role=row["role"],
            )
            for row in rows
        ],
        next_cursor=next_cursor,
    )


@router.get("/{opportunity_id}/shares", response_model=Page[SharePublic])
def list_shares_page(
    opportunity_id: int,
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[SharePublic]:
    """Ordered by name, tie-broken on `user_id` rather than on email: a
    cursor needs a column that is unique within the ordering.
    """
    continuation, cursor_values = cursor_clause(
        page,
        "shared_user.name",
        "opportunity_shares.user_id",
        descending=False,
    )
    params: list[object] = [opportunity_id, *cursor_values, page.limit + 1]

    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        rows = connection.execute(
            f"""
            {SHARE_ROWS_SQL}
            {f"AND {continuation}" if continuation else ""}
            ORDER BY shared_user.name ASC, opportunity_shares.user_id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["name"], row["user_id"]))
    return Page(items=[share_from_row(row) for row in rows], next_cursor=next_cursor)


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

        # The row may exist and be soft-deleted, which is why this is an
        # upsert and why it is shared with the ownership transfer that leaves
        # the previous owner behind as an editor (`share_utils.py`).
        upsert_share_row(
            connection,
            opportunity_id,
            int(invited_user["id"]),
            payload.role,
            int(user["id"]),
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

        soft_delete_share(connection, opportunity_id, user_id)
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


def audit_entry_from_row(row: sqlite3.Row) -> AuditLogEntryPublic:
    return AuditLogEntryPublic(
        id=row["id"],
        opportunity_id=row["opportunity_id"],
        actor_id=row["actor_id"],
        actor_name=row["actor_name"],
        action=row["action"],
        detail=parse_audit_detail(row["action"], row["detail"]),
        created_at=row["created_at"],
    )


@router.get("/{opportunity_id}/audit-log", response_model=Page[AuditLogEntryPublic])
def list_audit_log_page(
    opportunity_id: int,
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[AuditLogEntryPublic]:
    """Oldest first: the audit log is read as a narrative of what happened to
    the opportunity, so the page boundary walks forward in time.
    """
    continuation, cursor_values = cursor_clause(
        page,
        "audit_log_entries.created_at",
        "audit_log_entries.id",
        descending=False,
    )
    params: list[object] = [opportunity_id, *cursor_values, page.limit + 1]

    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        rows = connection.execute(
            f"""
            SELECT audit_log_entries.*, users.name AS actor_name
            FROM audit_log_entries
            LEFT JOIN users ON users.id = audit_log_entries.actor_id
            WHERE audit_log_entries.opportunity_id = ?
            {f"AND {continuation}" if continuation else ""}
            ORDER BY audit_log_entries.created_at ASC, audit_log_entries.id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["created_at"], row["id"]))
    return Page(items=[audit_entry_from_row(row) for row in rows], next_cursor=next_cursor)
