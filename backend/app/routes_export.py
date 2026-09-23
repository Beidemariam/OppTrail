import sqlite3
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response

from .auth import get_current_user
from .database import db_connection
from .export_service import (
    export_data_to_csv,
    export_data_to_pdf,
    fetch_export_data,
    safe_export_filename,
)
from .permissions import require_opportunity_access

router = APIRouter(prefix="/api/v2/opportunities", tags=["export"])


def content_disposition(filename: str) -> str:
    return f'attachment; filename="{filename}"'


def get_export_data(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> dict[str, Any]:
    require_opportunity_access(connection, opportunity_id, user_id)
    return fetch_export_data(connection, opportunity_id)


@router.get("/{opportunity_id}/export/json")
def export_json(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> JSONResponse:
    with db_connection() as connection:
        data = get_export_data(connection, opportunity_id, int(user["id"]))

    filename = safe_export_filename(data["opportunity"]["name"], "json")
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("/{opportunity_id}/export/csv")
def export_csv(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> Response:
    with db_connection() as connection:
        data = get_export_data(connection, opportunity_id, int(user["id"]))

    filename = safe_export_filename(data["opportunity"]["name"], "csv")
    return Response(
        content=export_data_to_csv(data),
        media_type="text/csv",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.get("/{opportunity_id}/export/pdf")
def export_pdf(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> Response:
    with db_connection() as connection:
        data = get_export_data(connection, opportunity_id, int(user["id"]))

    filename = safe_export_filename(data["opportunity"]["name"], "pdf")
    return Response(
        content=export_data_to_pdf(data),
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename)},
    )
