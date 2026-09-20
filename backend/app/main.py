import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .backup import latest_backup_at
from .database import db_connection, initialize_database
from .errors import error_body, install_error_handlers, is_v2_path
from .logging_utils import RequestLoggingMiddleware, configure_logging, logger
from .routes_ai import router as ai_router
from .routes_auth import router as auth_router
from .routes_export import router as export_router
from .routes_notifications import router as notifications_router
from .routes_notifications import v2_router as notifications_v2_router
from .routes_opportunities import router as opportunities_router
from .routes_opportunities import v2_router as opportunities_v2_router
from .routes_search import v2_router as search_v2_router
from .routes_sharing import router as sharing_router
from .routes_sharing import v2_router as sharing_v2_router
from .routes_timeline import router as timeline_router
from .routes_timeline import v2_router as timeline_v2_router
from .schemas import HealthStatus
from .security import CsrfMiddleware, SecurityHeadersMiddleware
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    initialize_database()
    yield


app = FastAPI(title="OppTrail API", version="0.1.0", lifespan=lifespan)
install_error_handlers(app)
# Starlette runs the most recently added middleware outermost, so this
# ordering is load bearing: request logging sees every response including the
# rejections below it, and the security headers are attached to the CSRF
# middleware's 403 as well as to real responses.
app.add_middleware(CsrfMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(auth_router)
app.include_router(opportunities_router)
app.include_router(sharing_router)
app.include_router(timeline_router)
app.include_router(ai_router)
app.include_router(export_router)
app.include_router(notifications_router)
# The v2 surface (`docs/ARCHITECTURE.md`, "API versioning"): the paginated
# collection reads and the `{"error": {...}}` envelope. v1 above is unchanged
# and keeps serving the shipped frontend until it moves.
app.include_router(opportunities_v2_router)
app.include_router(sharing_v2_router)
app.include_router(timeline_v2_router)
app.include_router(notifications_v2_router)
app.include_router(search_v2_router)


@app.get("/api/health", response_model=HealthStatus)
def health_check() -> HealthStatus:
    # `get_connection()` itself asserts WAL mode, which is a write -- so a
    # database that is genuinely unwritable (read-only mount, full disk) can
    # fail before a query ever runs. The whole probe is one try block rather
    # than just the `BEGIN IMMEDIATE` below, so that case is reported as
    # `database_writable: false` instead of a 500 from the liveness endpoint.
    schema_version = "unknown"
    database_writable = False
    try:
        with db_connection() as connection:
            version_row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            schema_version = version_row["version_num"] if version_row else "unknown"
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
            database_writable = True
    except sqlite3.OperationalError as exc:
        logger.warning("health_check_database_not_writable", exc_info=exc)

    return HealthStatus(
        status="ok",
        schema_version=schema_version,
        database_writable=database_writable,
        last_backup_at=latest_backup_at(),
    )


frontend_dir = Path(settings.frontend_static_dir)
next_assets_dir = frontend_dir / "_next"

if next_assets_dir.exists():
    app.mount("/_next", StaticFiles(directory=next_assets_dir), name="next-assets")


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
def api_not_found(request: Request, path: str) -> JSONResponse:
    if is_v2_path(request.url.path):
        return JSONResponse(error_body(404, "API endpoint not found"), status_code=404)
    return JSONResponse({"detail": "API endpoint not found"}, status_code=404)


@app.get("/{path:path}", include_in_schema=False, response_model=None)
def serve_frontend(path: str) -> FileResponse | JSONResponse:
    # `path` is attacker-controlled and arrives percent-decoded, so it can carry
    # ".." segments. Resolve first and serve only what stays inside the build.
    static_root = frontend_dir.resolve()
    requested_path = (static_root / path).resolve()
    if requested_path.is_relative_to(static_root) and requested_path.is_file():
        return FileResponse(requested_path)

    index_path = frontend_dir / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)

    return JSONResponse({"detail": "Frontend build not found"}, status_code=404)
