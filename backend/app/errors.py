from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .logging_utils import REQUEST_ID_HEADER, logger
from .settings import settings


def install_error_handlers(app: FastAPI) -> None:
    """Every error response is `{"detail": str}`, matching FastAPI's own shape
    for `HTTPException` and validation errors, so `apiRequest<T>()` on the
    frontend (CLAUDE.md: "throws on non-2xx using the API's `detail` field")
    handles every error path the same way. Without this handler, an unhandled
    exception falls through to Starlette's default plain-text 500, which is
    not JSON and breaks that contract.

    Starlette special-cases a handler registered for the bare `Exception`
    class: it runs inside `ServerErrorMiddleware`, which sits *above*
    `RequestLoggingMiddleware` in the stack, so the response this handler
    returns never passes through that middleware's `send_wrapper`. The
    `X-Request-ID` header has to be set here directly, or error responses
    would be the one response class missing it.
    """

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
        return JSONResponse({"detail": detail}, status_code=500, headers=headers)
