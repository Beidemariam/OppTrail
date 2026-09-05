from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import initialize_database
from .routes_ai import router as ai_router
from .routes_auth import router as auth_router
from .routes_export import router as export_router
from .routes_notifications import router as notifications_router
from .routes_opportunities import router as opportunities_router
from .routes_sharing import router as sharing_router
from .routes_timeline import router as timeline_router
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="OppTrail API", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(opportunities_router)
app.include_router(sharing_router)
app.include_router(timeline_router)
app.include_router(ai_router)
app.include_router(export_router)
app.include_router(notifications_router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


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
    return JSONResponse({"detail": "API endpoint not found"}, status_code=404)


@app.get("/{path:path}", include_in_schema=False)
def serve_frontend(path: str):
    requested_path = frontend_dir / path
    if requested_path.is_file():
        return FileResponse(requested_path)

    index_path = frontend_dir / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)

    return JSONResponse({"detail": "Frontend build not found"}, status_code=404)
