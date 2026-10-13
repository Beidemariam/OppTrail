import json
import sqlite3
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from .ai_filters import parse_filter_answer
from .ai_service import (
    ask_openai,
    ask_openai_for_filter,
    build_filter_prompt,
    build_timeline_context,
    extract_referenced_entry_numbers,
    normalize_ai_answer,
    stream_openai,
)
from .auth import get_current_user
from .database import read_only_connection
from .events import sse_frame
from .logging_utils import logger
from .permissions import require_opportunity_access
from .schemas import (
    FILTER_SORT_FIELDS,
    STAGES,
    AiAskRequest,
    AiAskResponse,
    AiFilterRequest,
    AiFilterResponse,
)
from .settings import settings
from .time_utils import utc_now

router = APIRouter(prefix="/api/v2/opportunities", tags=["ai"])
# The filter proposal is about the board rather than about one deal, so it
# does not belong under an opportunity's path (milestone 6.4).
filter_router = APIRouter(prefix="/api/v2/ai", tags=["ai"])


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

    # Read-only by construction, not by instruction (brief §2.1): this
    # connection refuses writes at the SQLite level.
    with read_only_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))
        timeline_context, entry_numbers = build_timeline_context(
            connection, opportunity_id, payload.since, payload.until
        )

    try:
        answer = ask_openai(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeline_context=timeline_context,
            question=payload.question,
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
            reasoning_effort=settings.openai_reasoning_effort,
        )
    except Exception as exc:
        logger.warning(
            "ai_agent_call_failed",
            exc_info=exc,
            extra={"opportunity_id": opportunity_id},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service is unavailable",
        ) from exc

    return AiAskResponse(
        answer=answer,
        referenced_entry_numbers=extract_referenced_entry_numbers(answer, entry_numbers),
    )


@router.post("/{opportunity_id}/ai/ask/stream")
def stream_ai_answer(
    opportunity_id: int,
    payload: AiAskRequest,
    user: sqlite3.Row = Depends(get_current_user),
) -> StreamingResponse:
    """The same answer as `ask`, arriving as it is written (milestone 6.4).

    §14 asks for streaming, and on this deployment it is what makes the
    feature usable: D-168 measured a reasoning model's floor at ~29 seconds,
    and forty seconds of spinner is indistinguishable from a broken button.

    **A POST that answers `text/event-stream`**, which is a different shape
    from ADR 0003's live updates and deliberately so. That stream is a GET
    read by `EventSource`, carries invalidations and never content, and lives
    as long as a screen does. This one carries content, is answered once, and
    needs a request body -- the question -- which `EventSource` cannot send.
    So the client reads it with `fetch` and a reader (`lib/aiStream.ts`), and
    the framing is SSE only because the two halves of the answer have to be
    told apart.

    Two event types, for that reason:

    - `delta`, a piece of the answer as plain text;
    - `done`, carrying the entry numbers the finished answer cited, which is
      computed from the whole text and so cannot be known until the end. The
      client shows the same citations the non-streaming path returns rather
      than reimplementing `extract_referenced_entry_numbers`.

    A failure mid-stream cannot become a 502: the status line is long gone by
    then. It is an `error` event, and the client shows it where the answer
    was going to be.
    """
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured",
        )

    # The permission check and the context read happen *before* the response
    # starts, so a reader with no access still gets an ordinary 404 rather
    # than a 200 whose first frame is an error.
    with read_only_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))
        timeline_context, entry_numbers = build_timeline_context(
            connection, opportunity_id, payload.since, payload.until
        )

    def frames() -> Iterator[str]:
        answer: list[str] = []
        try:
            for delta in stream_openai(
                api_key=settings.openai_api_key or "",
                model=settings.openai_model,
                timeline_context=timeline_context,
                question=payload.question,
                timeout=settings.openai_timeout_seconds,
                max_retries=settings.openai_max_retries,
                reasoning_effort=settings.openai_reasoning_effort,
            ):
                answer.append(delta)
                yield sse_frame("delta", delta)
        except Exception as exc:
            logger.warning(
                "ai_stream_failed",
                exc_info=exc,
                extra={"opportunity_id": opportunity_id},
            )
            yield sse_frame("error", "AI service is unavailable")
            return

        whole = normalize_ai_answer("".join(answer))
        yield sse_frame(
            "done",
            json.dumps(
                {
                    "answer": whole,
                    "referenced_entry_numbers": extract_referenced_entry_numbers(
                        whole, entry_numbers
                    ),
                }
            ),
        )

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"cache-control": "no-store", "x-accel-buffering": "no"},
    )


@filter_router.post("/filter", response_model=AiFilterResponse)
def propose_filter(
    payload: AiFilterRequest,
    user: sqlite3.Row = Depends(get_current_user),
) -> AiFilterResponse:
    """A sentence, as a filter the reader can look at before applying it.

    `docs/FEATURES.md` §14: *"deals stuck in negotiation over 50k produces a
    filter the user sees and applies. This is the safest high-value AI
    feature here, because its output is a query the user can inspect."*

    Three things make that true rather than merely said:

    - **Nothing is applied here.** The answer is a proposal; applying it is
      the reader pressing a button, which writes the same URL parameters the
      filter bar writes. The AI is the actor in nothing (ADR 0012).
    - **The model's JSON is never trusted** (**D-186**). `ai_filters.py`
      parses it against the vocabulary this board actually has and reports
      what it dropped, so what is shown is exactly what would be applied.
    - **No deal content is sent.** This answers from the request sentence and
      the stage and sort names alone -- a question about the shape of a list
      needs nobody's timeline, so none goes.

    Not opportunity-scoped, so it is on its own router: the filter is over
    the board, and every signed-in caller has a board. The rows it later
    selects are permission-filtered by the ordinary list read, as they are
    for a saved view somebody shared (D-060).
    """
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured",
        )

    try:
        answer = ask_openai_for_filter(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            instructions=build_filter_prompt(STAGES, list(FILTER_SORT_FIELDS), utc_now()[:10]),
            request=payload.request,
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
            reasoning_effort=settings.openai_reasoning_effort,
        )
    except Exception as exc:
        logger.warning("ai_filter_call_failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service is unavailable",
        ) from exc

    return parse_filter_answer(answer)
