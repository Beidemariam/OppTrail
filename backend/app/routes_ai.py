import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from .ai_service import (
    ask_openai,
    build_timeline_context,
    extract_referenced_entry_ids,
)
from .auth import get_current_user
from .database import db_connection
from .permissions import require_opportunity_access
from .schemas import AiAskRequest, AiAskResponse
from .settings import settings


router = APIRouter(prefix="/api/opportunities", tags=["ai"])


@router.post("/{opportunity_id}/ai/ask", response_model=AiAskResponse)
def ask_ai_agent(
    opportunity_id: int,
    payload: AiAskRequest,
    user: sqlite3.Row = Depends(get_current_user),
) -> AiAskResponse:
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured",
        )

    with db_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))
        timeline_context, entry_ids = build_timeline_context(connection, opportunity_id)

    try:
        answer = ask_openai(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeline_context=timeline_context,
            question=payload.question,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service is unavailable",
        ) from exc

    return AiAskResponse(
        answer=answer,
        referenced_entry_ids=extract_referenced_entry_ids(answer, entry_ids),
    )
