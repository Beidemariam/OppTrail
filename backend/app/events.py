"""The live-update transport: one in-process publisher, one SSE stream per
reader (ADR 0003).

What travels is an **invalidation**, never a payload: the server says
`{"type": "timeline.changed", "opportunity_id": 7}` and the client refetches
through its ordinary data layer. That is the whole reason this module holds no
row-shaping code — a push path that carried content would be a second place
authorization and serialization are decided, and the two would drift.

Three things about it are load bearing:

- **Publish after `commit()`, never before.** A subscriber's only reaction is
  to read again, so an event that arrives while the writing transaction is
  still open sends it to fetch the state that is about to be replaced. Every
  call site in `routes_*.py` therefore sits below the commit, not beside the
  `INSERT`.
- **The queue de-duplicates, so it is bounded by the number of event types.**
  Two writes a millisecond apart mean one refetch, not two, and a reader that
  is slow to drain cannot make the writer's memory grow: `_Subscriber.pending`
  refuses an event already waiting. Coalescing is only sound because these are
  invalidations -- idempotent, and carrying no information a missed duplicate
  would lose.
- **A stream ends by itself.** `stream_events` closes after
  `settings.sse_max_connection_seconds` and emits a `retry:` field, so the
  browser's own `EventSource` reconnects; an SSE connection that is meant to
  live forever is one an intermediary eventually cuts with no reconnect
  advice. It is also what makes the endpoint testable at all -- Starlette's
  `TestClient` buffers a response whole (`tests/conftest.py`'s
  `short_event_streams`).

Publishing happens from the worker thread FastAPI runs a `def` endpoint in,
while every subscriber's queue belongs to the event loop serving its own
request. `_Subscriber` therefore stores that loop and `publish` hands the work
back to it with `call_soon_threadsafe`, which is the one thread-safe door into
an `asyncio.Queue`.
"""

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from .logging_utils import logger
from .settings import settings

# The two questions a reader of one opportunity can have gone stale about.
# `timeline.changed` covers everything hanging off the timeline -- entries,
# notes, comments, reactions, a resolved thread -- because the client reads
# them as one tree; `opportunity.changed` is the record itself, its stage, its
# sharing and its ownership.
EventType = Literal["timeline.changed", "opportunity.changed"]

# Sent once, immediately, so a client knows the stream is open rather than
# merely accepted, and so a test has something to assert without waiting for a
# write. It carries no opportunity id: it is about the connection.
READY_FRAME = "event: ready\ndata: {}\n\n"
# A comment line. Ignored by `EventSource`, but it is a byte on the wire, which
# is what keeps an idle connection from being reaped by an intermediary.
HEARTBEAT_FRAME = ": keepalive\n\n"


def sse_frame(event: str, data: str) -> str:
    """One SSE message carrying arbitrary text (milestone 6.4).

    `Event.frame` below formats this module's own invalidations, whose data
    is a single line of JSON by construction. The AI stream carries an
    answer, and an answer has newlines in it -- so each line needs its own
    `data:` prefix, which is how the spec says a multi-line payload travels
    and how the browser rejoins it with `\n`. A frame that forgot this would
    end the message at the first paragraph break and silently truncate every
    answer longer than one.

    An empty payload still emits one `data:` line: a frame with none is a
    comment, not an event.
    """
    lines = data.split("\n") or [""]
    body = "".join(f"data: {line}\n" for line in lines)
    return f"event: {event}\n{body}\n"


def retry_frame(seconds: float) -> str:
    """The reconnect delay `EventSource` should use when this stream ends.

    Set from the heartbeat rather than from a constant of its own: the point is
    to be back before the next heartbeat would have been due, so a closed
    window is invisible to the reader.
    """
    return f"retry: {int(seconds * 1000)}\n\n"


@dataclass(frozen=True)
class Event:
    type: EventType
    opportunity_id: int

    def frame(self) -> str:
        """One SSE message: a named event and a single JSON `data` line."""
        payload = json.dumps(
            {"type": self.type, "opportunity_id": self.opportunity_id},
            sort_keys=True,
        )
        return f"event: {self.type}\ndata: {payload}\n\n"


@dataclass(eq=False)
class _Subscriber:
    """One open stream. Compared by identity, so two readers of the same
    opportunity are two entries in the broker's set.
    """

    opportunity_id: int
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[Event]
    pending: set[Event] = field(default_factory=set)

    def offer(self, event: Event) -> None:
        """Queue an event unless an identical one is already waiting.

        Runs on `self.loop` -- `publish` schedules it there -- so touching
        `pending` and the queue together needs no lock of its own.
        """
        if event in self.pending:
            return
        self.pending.add(event)
        self.queue.put_nowait(event)

    async def next_event(self) -> Event:
        event = await self.queue.get()
        self.pending.discard(event)
        return event


class EventBroker:
    """The publish side. One instance per process (`broker` below), which is
    exactly the assumption ADR 0001 and ADR 0011 already make: one container,
    one FastAPI process, no message bus.
    """

    def __init__(self) -> None:
        # Publishers run in FastAPI's worker threads and subscribers register
        # from request event loops, so the set itself needs an ordinary lock.
        self._lock = threading.Lock()
        self._subscribers: set[_Subscriber] = set()

    def subscribe(self, opportunity_id: int) -> _Subscriber:
        """Register the calling coroutine's queue. Must be awaited-from: it
        reads the running loop so `publish` can reach it from a worker thread.
        """
        subscriber = _Subscriber(
            opportunity_id=opportunity_id,
            loop=asyncio.get_running_loop(),
            queue=asyncio.Queue(),
        )
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: _Subscriber) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def subscriber_count(self, opportunity_id: int) -> int:
        """How many streams are open on one opportunity.

        Written for the tests: a write published before its reader has
        registered is a write the reader never sees, so a test that means to
        observe delivery waits on this rather than on a sleep (brief §6.5).
        """
        with self._lock:
            return sum(1 for one in self._subscribers if one.opportunity_id == opportunity_id)

    def publish(self, opportunity_id: int, event_type: EventType) -> None:
        """Tell every open stream on this opportunity to read again.

        Thread-safe and non-blocking, because it is called from a request
        handler that has just committed and has nothing to gain by waiting.
        """
        event = Event(type=event_type, opportunity_id=opportunity_id)
        with self._lock:
            targets = [one for one in self._subscribers if one.opportunity_id == opportunity_id]

        for subscriber in targets:
            try:
                subscriber.loop.call_soon_threadsafe(subscriber.offer, event)
            except RuntimeError:
                # The loop closed between the snapshot above and here: the
                # reader has gone and its own `finally` is about to
                # unsubscribe. Nothing to deliver and nothing to repair.
                logger.debug(
                    "event_subscriber_loop_closed",
                    extra={"opportunity_id": opportunity_id},
                )


broker = EventBroker()


def publish_timeline_changed(opportunity_id: int) -> None:
    broker.publish(opportunity_id, "timeline.changed")


def publish_opportunity_changed(opportunity_id: int) -> None:
    broker.publish(opportunity_id, "opportunity.changed")


async def stream_events(opportunity_id: int) -> AsyncIterator[str]:
    """The body of `GET /api/v2/opportunities/{id}/events`.

    Permission is resolved by the route before this is entered: an async
    generator's first line does not run until the response is already being
    sent, so a check in here would answer 200 and then fail mid-stream.
    """
    max_seconds = settings.sse_max_connection_seconds
    heartbeat_seconds = settings.sse_heartbeat_seconds
    loop = asyncio.get_running_loop()
    subscriber = broker.subscribe(opportunity_id)
    try:
        yield retry_frame(heartbeat_seconds)
        yield READY_FRAME
        deadline = loop.time() + max_seconds
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            try:
                event = await asyncio.wait_for(
                    subscriber.next_event(),
                    timeout=min(heartbeat_seconds, remaining),
                )
            except TimeoutError:
                yield HEARTBEAT_FRAME
                continue
            yield event.frame()
    finally:
        broker.unsubscribe(subscriber)
