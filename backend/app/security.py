"""Transport-level hardening that applies to every response: CSRF protection for
the cookie session and the response security headers (brief §4.5).

Both are plain ASGI middleware rather than `BaseHTTPMiddleware`, for the reason
recorded on `logging_utils.RequestLoggingMiddleware`.
"""

import secrets

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import error_body, is_v2_path
from .settings import settings

CSRF_COOKIE_NAME = "opptrail_csrf"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_COOKIE_MAX_AGE = 7 * 24 * 60 * 60
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# `script-src`/`style-src` allow inline because `output: "export"` emits the
# hydration payload as inline <script> blocks (frontend/out/index.html) and
# there is no server-side render to attach a per-request nonce to. Everything
# else is locked to same-origin; `frame-ancestors 'none'` is the clickjacking
# control brief §4.5 asks for.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "img-src 'self' data:",
        "style-src 'self' 'unsafe-inline'",
        "script-src 'self' 'unsafe-inline'",
        "connect-src 'self'",
    )
)
SECURITY_HEADERS = {
    "content-security-policy": CONTENT_SECURITY_POLICY,
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}


def cookies_are_secure() -> bool:
    """`Secure` is set in production only: development and the test suite both
    speak plain HTTP to localhost, where a `Secure` cookie is simply dropped.
    """
    return settings.environment == "production"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_set_cookie_header(token: str) -> str:
    """Deliberately not `HttpOnly` — the frontend has to read this value back to
    echo it in `X-CSRF-Token`. That is safe for a double-submit token: it is not
    a credential on its own, and the session cookie stays `HttpOnly`.
    """
    attributes = [
        f"{CSRF_COOKIE_NAME}={token}",
        "Path=/",
        f"Max-Age={CSRF_COOKIE_MAX_AGE}",
        "SameSite=lax",
    ]
    if cookies_are_secure():
        attributes.append("Secure")
    return "; ".join(attributes)


class SecurityHeadersMiddleware:
    """Adds `SECURITY_HEADERS` to every response, including error responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_wrapper)


class CsrfMiddleware:
    """Double-submit-cookie CSRF protection for the cookie session.

    A cross-site attacker can make the browser send the `HttpOnly` session
    cookie, but same-origin policy stops it reading `opptrail_csrf` back, so it
    cannot populate the matching `X-CSRF-Token` header. Every unsafe method is
    rejected without that pair, login and signup included: a client bootstraps
    the token from any safe request (the SPA gets one with `GET /`), and a
    rejected request carries a fresh cookie so the retry succeeds.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cookie_token = Request(scope).cookies.get(CSRF_COOKIE_NAME)
        token = cookie_token or new_csrf_token()

        if scope["method"] not in SAFE_METHODS and not self._is_verified(scope, cookie_token):
            # Rejected before routing, so this is the one error a v2 client can
            # see that no exception handler produces; it carries the v2 envelope
            # itself rather than leaving one path on the v1 shape.
            message = "CSRF token missing or invalid"
            body = error_body(403, message) if is_v2_path(scope["path"]) else {"detail": message}
            response = JSONResponse(body, status_code=403)
            response.raw_headers.append(
                (b"set-cookie", csrf_set_cookie_header(token).encode("latin-1"))
            )
            await response(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and cookie_token is None:
                headers = MutableHeaders(scope=message)
                headers.append("set-cookie", csrf_set_cookie_header(token))
            await send(message)

        await self.app(scope, receive, send_wrapper)

    @staticmethod
    def _is_verified(scope: Scope, cookie_token: str | None) -> bool:
        supplied = Headers(scope=scope).get(CSRF_HEADER_NAME)
        if cookie_token is None or supplied is None:
            return False
        return secrets.compare_digest(supplied, cookie_token)
