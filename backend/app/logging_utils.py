import json
import logging
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
LOG_RECORD_FIELDS = (
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "opportunity_id",
)

logger = logging.getLogger("opptrail")


class JsonFormatter(logging.Formatter):
    """Emits one JSON object per line; never includes request/response bodies,
    headers, or cookies, so session tokens and passwords cannot leak into logs.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in LOG_RECORD_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
            payload["exception_message"] = str(record.exc_info[1])
        return json.dumps(payload)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False


class RequestLoggingMiddleware:
    """Pure ASGI middleware, not `BaseHTTPMiddleware` (`@app.middleware("http")`):
    the latter runs `call_next` in its own anyio task group and is documented to
    mishandle/swallow exceptions raised by sync routes executed in the worker
    threadpool (starlette#1678 and related issues), which surfaced here as an
    order-dependent test failure — the exact non-determinism brief §6.5 forbids.
    A raw ASGI middleware has no such interaction with the exception-handling
    path.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope["state"]["request_id"] = request_id
        start = time.monotonic()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers.append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "method": scope["method"],
                    "path": scope["path"],
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
