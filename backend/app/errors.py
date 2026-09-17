"""The two API error shapes, and the rule for which path gets which.

v1 (`/api/*`) answers `{"detail": ...}` — FastAPI's own shape, which the
shipped frontend's `apiRequest<T>()` reads (CLAUDE.md: it "throws on non-2xx
using the API's `detail` field"). It does not change while it is still serving
that frontend (`docs/ROADMAP.md` Phase 1 acceptance: "v1 endpoints still serve
the existing frontend").

v2 (`/api/v2/*`) answers the single envelope `docs/ARCHITECTURE.md` specifies:
`{"error": {"code", "message", "fields"?}}`. `fields` exists only on a
validation failure, and it is the half that matters: today a 422 reaches the UI
as a flat "Request failed" and the user never learns which field was wrong
(`docs/REVIEW.md` M4).

Every error path is routed through here, including the ones that never reach a
route handler — an unknown path, a CSRF rejection — so a v2 client has exactly
one failure shape to parse.
"""

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from .logging_utils import REQUEST_ID_HEADER, logger
from .settings import settings

V2_PREFIX = "/api/v2"

# Named codes rather than the bare status number: a client branches on
# `error.code`, and "not_found" survives a status change that "404" would not.
ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}
FALLBACK_ERROR_CODE = "internal_error"


def is_v2_path(path: str) -> bool:
    return path == V2_PREFIX or path.startswith(f"{V2_PREFIX}/")


def error_body(
    status_code: int,
    message: str,
    fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": ERROR_CODES.get(status_code, FALLBACK_ERROR_CODE),
        "message": message,
    }
    if fields is not None:
        error["fields"] = fields
    return {"error": error}


def error_response(
    status_code: int,
    message: str,
    fields: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        error_body(status_code, message, fields),
        status_code=status_code,
        headers=headers,
    )


def validation_fields(errors: list[Any]) -> dict[str, str]:
    """Pydantic's error list flattened to one message per field.

    The location tuple starts with the source ("body", "query", "path"), which
    is dropped: a client knows where it put the value, and "stage" is a usable
    key for a form while "body.stage" is not. Nested locations keep their dots.
    The first error per field wins — a field with two failures still only has
    one input to correct.
    """
    fields: dict[str, str] = {}
    for error in errors:
        location = [str(part) for part in error.get("loc", ())][1:]
        key = ".".join(location) if location else "_"
        fields.setdefault(key, error.get("msg", "Invalid value"))
    return fields


def install_error_handlers(app: FastAPI) -> None:
    """Registers the three handlers that cover every failure the app can emit.

    Starlette special-cases a handler registered for the bare `Exception`
    class: it runs inside `ServerErrorMiddleware`, which sits *above*
    `RequestLoggingMiddleware` in the stack, so the response that handler
    returns never passes through that middleware's `send_wrapper`. The
    `X-Request-ID` header has to be set there directly, or error responses
    would be the one response class missing it.
    """

    @app.exception_handler(HTTPException)
    async def http_exception_envelope(request: Request, exc: HTTPException) -> Response:
        if not is_v2_path(request.url.path):
            return await http_exception_handler(request, exc)
        return error_response(
            exc.status_code,
            str(exc.detail),
            headers=dict(exc.headers) if exc.headers else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_envelope(request: Request, exc: RequestValidationError) -> Response:
        if not is_v2_path(request.url.path):
            return await request_validation_exception_handler(request, exc)
        return error_response(
            422,
            "The request could not be validated",
            fields=validation_fields(list(exc.errors())),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "unhandled_exception",
            exc_info=exc,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        detail = "Internal server error" if settings.environment == "production" else str(exc)
        headers = {REQUEST_ID_HEADER: request_id} if request_id else None
        if is_v2_path(request.url.path):
            return error_response(500, detail, headers=headers)
        return JSONResponse({"detail": detail}, status_code=500, headers=headers)
