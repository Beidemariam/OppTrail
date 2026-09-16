import sqlite3
from decimal import Decimal

from fastapi import APIRouter, Depends, status

from .audit_utils import create_audit_log_entry
from .auth import get_current_user
from .database import db_connection
from .permissions import Role, require_opportunity_access, require_opportunity_owner
from .schemas import (
    STAGES,
    OpportunityCreate,
    OpportunityListResponse,
    OpportunityPublic,
    OpportunityUpdate,
)
from .time_utils import utc_days_ago
from .timeline_utils import create_system_timeline_entry

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


STALLED_AFTER_DAYS = 14


def is_opportunity_stalled(
    connection: sqlite3.Connection,
    opportunity_id: int,
) -> bool:
    """True when nothing has happened on the opportunity for 14 days.

    Every timestamp is stored as fixed-width UTC ISO-8601, so SQLite can pick
    the latest activity and compare it to the cutoff as a plain string.
    """
    latest_activity = connection.execute(
        """
        SELECT MAX(activity_at) AS latest_activity
        FROM (
            SELECT event_timestamp AS activity_at
            FROM timeline_entries
            WHERE opportunity_id = ? AND deleted_at IS NULL
            UNION ALL
            SELECT notes.created_at AS activity_at
            FROM notes
            JOIN timeline_entries ON timeline_entries.id = notes.entry_id
            WHERE timeline_entries.opportunity_id = ?
                AND timeline_entries.deleted_at IS NULL
                AND notes.deleted_at IS NULL
            UNION ALL
            SELECT comments.created_at AS activity_at
            FROM comments
            JOIN notes ON notes.id = comments.note_id
            JOIN timeline_entries ON timeline_entries.id = notes.entry_id
            WHERE timeline_entries.opportunity_id = ?
                AND timeline_entries.deleted_at IS NULL
                AND notes.deleted_at IS NULL
                AND comments.deleted_at IS NULL
        )
        """,
        (opportunity_id, opportunity_id, opportunity_id),
    ).fetchone()["latest_activity"]

    if latest_activity is None:
        return False
    return bool(latest_activity < utc_days_ago(STALLED_AFTER_DAYS))


def opportunity_from_row(row: sqlite3.Row, role: Role, stalled: bool = False) -> OpportunityPublic:
    return OpportunityPublic(
        id=row["id"],
        name=row["name"],
        account_name=row["account_name"],
        value=Decimal(str(row["value"])),
        currency=row["currency"],
        stage=row["stage"],
        owner_id=row["owner_id"],
        owner_name=row["owner_name"],
        expected_close_date=row["expected_close_date"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        stalled=stalled,
        current_user_role=role,
    )


def fetch_opportunity_row(
    connection: sqlite3.Connection,
    opportunity_id: int,
) -> sqlite3.Row | None:
    """Plain opportunity lookup. Callers resolve role via `permissions.py`."""
    row: sqlite3.Row | None = connection.execute(
        """
        SELECT opportunities.*, users.name AS owner_name
        FROM opportunities
        JOIN users ON users.id = opportunities.owner_id
        WHERE opportunities.id = ? AND opportunities.deleted_at IS NULL
        """,
        (opportunity_id,),
    ).fetchone()
    return row


@router.get("", response_model=OpportunityListResponse)
def list_opportunities(
    user: sqlite3.Row = Depends(get_current_user),
) -> OpportunityListResponse:
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT
                opportunities.*,
                users.name AS owner_name,
                CASE
                    WHEN opportunities.owner_id = ? THEN 'owner'
                    ELSE opportunity_shares.role
                END AS current_user_role
            FROM opportunities
            JOIN users ON users.id = opportunities.owner_id
            LEFT JOIN opportunity_shares
                ON opportunity_shares.opportunity_id = opportunities.id
                AND opportunity_shares.deleted_at IS NULL
            WHERE opportunities.deleted_at IS NULL
                AND (
                    opportunities.owner_id = ?
                    OR opportunity_shares.user_id = ?
                )
            ORDER BY opportunities.updated_at DESC, opportunities.id DESC
            """,
            (user["id"], user["id"], user["id"]),
        ).fetchall()

        opportunities = [
            opportunity_from_row(
                row, row["current_user_role"], is_opportunity_stalled(connection, row["id"])
            )
            for row in rows
        ]

    return OpportunityListResponse(stages=STAGES, opportunities=opportunities)


@router.post("", response_model=OpportunityPublic, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: OpportunityCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> OpportunityPublic:
    with db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO opportunities (
                name,
                account_name,
                value,
                currency,
                stage,
                owner_id,
                expected_close_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.account_name,
                str(payload.value),
                payload.currency,
                payload.stage,
                user["id"],
                payload.expected_close_date,
            ),
        )
        assert cursor.lastrowid is not None
        opportunity_id = int(cursor.lastrowid)
        create_system_timeline_entry(
            connection=connection,
            opportunity_id=opportunity_id,
            created_by=int(user["id"]),
            entry_type="other",
            title="Opportunity created",
            body=f"{payload.name} was created for {payload.account_name}.",
        )
        connection.commit()
        row = fetch_opportunity_row(connection, opportunity_id)
        stalled = is_opportunity_stalled(connection, opportunity_id)

    assert row is not None
    return opportunity_from_row(row, "owner", stalled)


@router.get("/{opportunity_id}", response_model=OpportunityPublic)
def get_opportunity(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> OpportunityPublic:
    with db_connection() as connection:
        role = require_opportunity_access(connection, opportunity_id, int(user["id"]))
        row = fetch_opportunity_row(connection, opportunity_id)
        stalled = is_opportunity_stalled(connection, opportunity_id)

    assert row is not None
    return opportunity_from_row(row, role, stalled)


@router.patch("/{opportunity_id}", response_model=OpportunityPublic)
def update_opportunity(
    opportunity_id: int,
    payload: OpportunityUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> OpportunityPublic:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        with db_connection() as connection:
            require_opportunity_owner(connection, opportunity_id, int(user["id"]))
            row = fetch_opportunity_row(connection, opportunity_id)
            stalled = is_opportunity_stalled(connection, opportunity_id)
        assert row is not None
        return opportunity_from_row(row, "owner", stalled)

    assignments = [f"{field} = ?" for field in updates]
    values = [str(value) if isinstance(value, Decimal) else value for value in updates.values()]
    values.extend([opportunity_id, user["id"]])

    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        row = fetch_opportunity_row(connection, opportunity_id)
        assert row is not None
        previous_stage = row["stage"]

        connection.execute(
            f"""
            UPDATE opportunities
            SET {", ".join(assignments)}, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE id = ? AND owner_id = ? AND deleted_at IS NULL
            """,
            values,
        )
        if updates.get("stage") and updates["stage"] != previous_stage:
            create_system_timeline_entry(
                connection=connection,
                opportunity_id=opportunity_id,
                created_by=int(user["id"]),
                entry_type="stage_change",
                title=f"Stage changed to {updates['stage']}",
                body=f"Stage changed from {previous_stage} to {updates['stage']}.",
            )
        connection.commit()
        updated = fetch_opportunity_row(connection, opportunity_id)
        stalled = is_opportunity_stalled(connection, opportunity_id)

    assert updated is not None
    return opportunity_from_row(updated, "owner", stalled)


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        row = fetch_opportunity_row(connection, opportunity_id)
        assert row is not None

        connection.execute(
            """
            UPDATE comments
            SET deleted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE deleted_at IS NULL
                AND note_id IN (
                    SELECT notes.id
                    FROM notes
                    JOIN timeline_entries ON timeline_entries.id = notes.entry_id
                    WHERE timeline_entries.opportunity_id = ?
                )
            """,
            (opportunity_id,),
        )
        connection.execute(
            """
            UPDATE notes
            SET deleted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE deleted_at IS NULL
                AND entry_id IN (
                    SELECT id
                    FROM timeline_entries
                    WHERE opportunity_id = ?
                )
            """,
            (opportunity_id,),
        )
        connection.execute(
            """
            UPDATE timeline_entries
            SET deleted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE opportunity_id = ? AND deleted_at IS NULL
            """,
            (opportunity_id,),
        )
        connection.execute(
            """
            UPDATE opportunity_shares
            SET deleted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE opportunity_id = ? AND deleted_at IS NULL
            """,
            (opportunity_id,),
        )
        connection.execute(
            """
            UPDATE opportunities
            SET deleted_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE id = ? AND owner_id = ? AND deleted_at IS NULL
            """,
            (opportunity_id, user["id"]),
        )
        create_audit_log_entry(
            connection=connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="opportunity_deleted",
            detail={
                "name": row["name"],
                "account_name": row["account_name"],
                "stage": row["stage"],
            },
        )
        connection.commit()
