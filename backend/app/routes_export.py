import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response

from .auth import get_current_user
from .database import db_connection
from .export_service import (
    export_data_to_csv,
    export_data_to_pdf,
    fetch_export_data,
    fetch_opportunity_list_export,
    opportunity_list_to_csv,
    safe_export_filename,
)
from .permissions import require_opportunity_access
from .schemas import BULK_ACTION_MAX_IDS
from .time_utils import utc_now

router = APIRouter(prefix="/api/v2/opportunities", tags=["export"])


def content_disposition(filename: str) -> str:
    return f'attachment; filename="{filename}"'


def get_export_data(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
    order: str = "desc",
) -> dict[str, Any]:
    """`order` is the timeline's own reading order, passed through by the link
    the reader clicks (milestone 4.4b) -- so the document runs the way the
    screen it was exported from does."""
    require_opportunity_access(connection, opportunity_id, user_id)
    return fetch_export_data(connection, opportunity_id, order)


# --- Exporting a selection (milestone 3.0a) ---------------------------------
#
# The fifth action on `docs/UX.md`'s bulk action bar, and the one that is not
# a `POST /opportunities/bulk` action: it answers with a file rather than a
# per-item result, so it cannot share that endpoint's response (**D-107**). A
# `GET` with the ids in the query string is what lets the action bar be a
# plain link, the way the per-opportunity exports already are.
#
# These two paths are one segment shorter than the three per-opportunity ones
# below, so nothing here depends on the order the routes are registered in.


def parse_export_ids(raw: str) -> list[int]:
    """`?ids=3,1,2` as a list, or 400.

    Deduplicated, because selecting the same row twice should not export it
    twice, and capped at the same `BULK_ACTION_MAX_IDS` the bulk endpoint
    takes -- the selection this serves is made in the same action bar.
    """
    ids: list[int] = []
    for value in raw.split(","):
        candidate = value.strip()
        if not candidate.isdigit():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ids must be a comma-separated list of opportunity ids",
            )
        number = int(candidate)
        if number not in ids:
            ids.append(number)

    if not ids or len(ids) > BULK_ACTION_MAX_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ids must name between 1 and {BULK_ACTION_MAX_IDS} opportunities",
        )
    return ids


@router.get("/export/json")
def export_selection_json(
    ids: str = Query(description="Comma-separated opportunity ids"),
    user: sqlite3.Row = Depends(get_current_user),
) -> JSONResponse:
    with db_connection() as connection:
        opportunities = fetch_opportunity_list_export(
            connection, parse_export_ids(ids), int(user["id"])
        )

    return JSONResponse(
        content={"exported_at": utc_now(), "opportunities": opportunities},
        headers={"Content-Disposition": content_disposition("opportunities.json")},
    )


@router.get("/export/csv")
def export_selection_csv(
    ids: str = Query(description="Comma-separated opportunity ids"),
    user: sqlite3.Row = Depends(get_current_user),
) -> Response:
    with db_connection() as connection:
        opportunities = fetch_opportunity_list_export(
            connection, parse_export_ids(ids), int(user["id"])
        )

    return Response(
        content=opportunity_list_to_csv(opportunities),
        media_type="text/csv",
        headers={"Content-Disposition": content_disposition("opportunities.csv")},
    )


@router.get("/{opportunity_id}/export/json")
def export_json(
    opportunity_id: int,
    order: Literal["asc", "desc"] = "desc",
    user: sqlite3.Row = Depends(get_current_user),
) -> JSONResponse:
    with db_connection() as connection:
        data = get_export_data(connection, opportunity_id, int(user["id"]), order)

    filename = safe_export_filename(data["opportunity"]["name"], "json")
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("/{opportunity_id}/export/csv")
def export_csv(
    opportunity_id: int,
    order: Literal["asc", "desc"] = "desc",
    user: sqlite3.Row = Depends(get_current_user),
) -> Response:
    with db_connection() as connection:
        data = get_export_data(connection, opportunity_id, int(user["id"]), order)

    filename = safe_export_filename(data["opportunity"]["name"], "csv")
    return Response(
        content=export_data_to_csv(data),
        media_type="text/csv",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("/{opportunity_id}/export/pdf")
def export_pdf(
    opportunity_id: int,
    order: Literal["asc", "desc"] = "desc",
    user: sqlite3.Row = Depends(get_current_user),
) -> Response:
    with db_connection() as connection:
        data = get_export_data(connection, opportunity_id, int(user["id"]), order)

    filename = safe_export_filename(data["opportunity"]["name"], "pdf")
    return Response(
        content=export_data_to_pdf(data),
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename)},
    )
