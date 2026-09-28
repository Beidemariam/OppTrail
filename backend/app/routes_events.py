"""The live-update stream (ADR 0003, milestone 3.4).

One route, and it is the only one in the app that does not answer JSON: it
holds the connection open and writes `text/event-stream` frames as other
people's writes land. `app/events.py` holds the transport; this file is the
permission boundary in front of it.
"""

import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from .auth import get_current_user
from .database import db_connection
from .events import stream_events
from .permissions import require_opportunity_access

router = APIRouter(prefix="/api/v2/opportunities", tags=["events"])


@router.get(
    "/{opportunity_id}/events",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "An `text/event-stream` of invalidation events for this "
                "opportunity: `ready` once the stream is open, then "
                "`timeline.changed` and `opportunity.changed` as other "
                "clients write. Each `data` line is "
                '`{"type": ..., "opportunity_id": ...}`; no row content is '
                "pushed, so a reader refetches through the ordinary API."
            ),
            "content": {"text/event-stream": {}},
        }
    },
)
def opportunity_events(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> StreamingResponse:
    """Any role may listen -- this is `require_opportunity_access`, the same
    gate as reading the timeline, because that is exactly what an event tells
    the client to do again.

    The check runs here rather than inside the generator on purpose: an async
    generator's body does not start until the response is already being sent,
    so a 403 raised in there would arrive after a 200 status line. What the
    stream never re-checks is a role that changes mid-connection -- a share
    removed while someone is listening leaves them a stream of
    *invalidations*, and the refetch each one provokes is the read that
    answers 404. No content reaches them through this path either way.

    `def` rather than `async def` because the permission check is a synchronous
    SQLite read, like every other route here. That costs a threadpool slot for
    the length of that one query only: the generator handed to
    `StreamingResponse` is iterated on the event loop, so an open stream holds
    a connection and not a worker -- a better bound than ADR 0003's
    consequences assume.
    """
    with db_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))

    return StreamingResponse(
        stream_events(opportunity_id),
        media_type="text/event-stream",
        headers={
            # A stream must not be cached, and must not be buffered by a
            # reverse proxy that would otherwise hold frames back until the
            # response it is waiting for never ends. `X-Accel-Buffering` is
            # nginx's opt-out; harmless everywhere else.
            "cache-control": "no-store",
            "x-accel-buffering": "no",
        },
    )
