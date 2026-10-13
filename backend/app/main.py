import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .backup import latest_backup_at
from .database import db_connection, initialize_database
from .errors import error_body, install_error_handlers
from .jobs import job_run_from_row, latest_job_runs
from .logging_utils import RequestLoggingMiddleware, configure_logging, logger
from .routes_ai import filter_router as ai_filter_router
from .routes_ai import router as ai_router
from .routes_attachments import router as attachments_router
from .routes_auth import router as auth_router
from .routes_automations import jobs_router as job_runs_router
from .routes_automations import router as automations_router
from .routes_custom_fields import router as custom_fields_router
from .routes_dashboard import router as dashboard_router
from .routes_events import router as events_router
from .routes_export import router as export_router
from .routes_notifications import router as notifications_router
from .routes_opportunities import router as opportunities_router
from .routes_saved_views import router as saved_views_router
from .routes_search import router as search_router
from .routes_sharing import router as sharing_router
from .routes_tasks import router as tasks_router
from .routes_timeline import router as timeline_router
from .scheduler import start_scheduler, stop_scheduler
from .schemas import HealthStatus, JobRunPublic
from .security import CsrfMiddleware, SecurityHeadersMiddleware
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    initialize_database()
    # ADR 0004's scheduler (milestone 6.5), started after the schema exists
    # because its first job reads `automation_rules`. Switched off by
    # `settings.scheduler_enabled`, which the test suite sets.
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="OppTrail API", version="0.1.0", lifespan=lifespan)
install_error_handlers(app)
# Starlette runs the most recently added middleware outermost, so this
# ordering is load bearing: request logging sees every response including the
# rejections below it, and the security headers are attached to the CSRF
# middleware's 403 as well as to real responses.
app.add_middleware(CsrfMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
# One API surface, `/api/v2/*` (`docs/ARCHITECTURE.md`, "API versioning"):
# paginated collection reads and the `{"error": {...}}` envelope throughout.
# v1 served the MVP frontend until milestone 2.9 moved it and was removed
# there, as `docs/ROADMAP.md`'s breaking-changes table schedules.
app.include_router(auth_router)
app.include_router(opportunities_router)
app.include_router(sharing_router)
app.include_router(timeline_router)
app.include_router(ai_router)
app.include_router(ai_filter_router)
app.include_router(export_router)
app.include_router(notifications_router)
app.include_router(search_router)
app.include_router(events_router)
app.include_router(saved_views_router)
app.include_router(tasks_router)
app.include_router(attachments_router)
app.include_router(custom_fields_router)
app.include_router(dashboard_router)
app.include_router(automations_router)
app.include_router(job_runs_router)


# Unversioned on purpose (D-094): this is an operations probe — the
# container's HEALTHCHECK, `scripts/docker-smoke.sh`, ADR 0011 — not part of
# the client surface the version boundary exists to move.
@app.get("/api/health", response_model=HealthStatus)
def health_check() -> HealthStatus:
    # `get_connection()` itself asserts WAL mode, which is a write -- so a
    # database that is genuinely unwritable (read-only mount, full disk) can
    # fail before a query ever runs. The whole probe is one try block rather
    # than just the `BEGIN IMMEDIATE` below, so that case is reported as
    # `database_writable: false` instead of a 500 from the liveness endpoint.
    schema_version = "unknown"
    database_writable = False
    jobs: list[JobRunPublic] = []
    try:
        with db_connection() as connection:
            version_row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            schema_version = version_row["version_num"] if version_row else "unknown"
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
            database_writable = True
            # Read inside the same `try` as everything else here: a probe
            # reports what it could learn, and a database it cannot open has
            # already been reported as unwritable above.
            jobs = [job_run_from_row(row) for row in latest_job_runs(connection)]
    except sqlite3.OperationalError as exc:
        logger.warning("health_check_database_not_writable", exc_info=exc)

    return HealthStatus(
        status="ok",
        schema_version=schema_version,
        database_writable=database_writable,
        last_backup_at=latest_backup_at(),
        jobs=jobs,
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
def api_not_found(path: str) -> JSONResponse:
    return JSONResponse(error_body(404, "API endpoint not found"), status_code=404)


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
