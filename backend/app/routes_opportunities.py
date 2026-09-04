import sqlite3
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import get_current_user
from .database import db_connection
from .schemas import (
    STAGES,
    OpportunityCreate,
    OpportunityListResponse,
    OpportunityPublic,
    OpportunityUpdate,
)
from .timeline_utils import create_system_timeline_entry


router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


def opportunity_from_row(row: sqlite3.Row) -> OpportunityPublic:
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
        stalled=False,
        current_user_role=row["current_user_role"],
    )


def fetch_accessible_opportunity(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
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
            AND opportunity_shares.user_id = ?
            AND opportunity_shares.deleted_at IS NULL
        WHERE opportunities.id = ?
            AND opportunities.deleted_at IS NULL
            AND (
                opportunities.owner_id = ?
                OR opportunity_shares.user_id IS NOT NULL
            )
        """,
        (user_id, user_id, opportunity_id, user_id),
    ).fetchone()


def fetch_owned_opportunity(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT opportunities.*, users.name AS owner_name, 'owner' AS current_user_role
        FROM opportunities
        JOIN users ON users.id = opportunities.owner_id
        WHERE opportunities.id = ?
            AND opportunities.owner_id = ?
            AND opportunities.deleted_at IS NULL
        """,
        (opportunity_id, user_id),
    ).fetchone()


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

    return OpportunityListResponse(
        stages=STAGES,
        opportunities=[opportunity_from_row(row) for row in rows],
    )


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
        row = fetch_owned_opportunity(connection, opportunity_id, int(user["id"]))

    return opportunity_from_row(row)


@router.get("/{opportunity_id}", response_model=OpportunityPublic)
def get_opportunity(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> OpportunityPublic:
    with db_connection() as connection:
        row = fetch_accessible_opportunity(connection, opportunity_id, int(user["id"]))

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    return opportunity_from_row(row)


@router.patch("/{opportunity_id}", response_model=OpportunityPublic)
def update_opportunity(
    opportunity_id: int,
    payload: OpportunityUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> OpportunityPublic:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        with db_connection() as connection:
            row = fetch_owned_opportunity(connection, opportunity_id, int(user["id"]))
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Opportunity not found",
            )
        return opportunity_from_row(row)

    assignments = [f"{field} = ?" for field in updates]
    values = [str(value) if isinstance(value, Decimal) else value for value in updates.values()]
    values.extend([opportunity_id, user["id"]])

    with db_connection() as connection:
        row = fetch_owned_opportunity(connection, opportunity_id, int(user["id"]))
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Opportunity not found",
            )
        previous_stage = row["stage"]

        connection.execute(
            f"""
            UPDATE opportunities
            SET {", ".join(assignments)}, updated_at = CURRENT_TIMESTAMP
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
        updated = fetch_owned_opportunity(connection, opportunity_id, int(user["id"]))

    return opportunity_from_row(updated)


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        row = fetch_owned_opportunity(connection, opportunity_id, int(user["id"]))
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Opportunity not found",
            )

        connection.execute(
            """
            UPDATE comments
            SET deleted_at = CURRENT_TIMESTAMP
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
            SET deleted_at = CURRENT_TIMESTAMP
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
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE opportunity_id = ? AND deleted_at IS NULL
            """,
            (opportunity_id,),
        )
        connection.execute(
            """
            UPDATE opportunity_shares
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE opportunity_id = ? AND deleted_at IS NULL
            """,
            (opportunity_id,),
        )
        connection.execute(
            """
            UPDATE opportunities
            SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND owner_id = ? AND deleted_at IS NULL
            """,
            (opportunity_id, user["id"]),
        )
        connection.commit()
