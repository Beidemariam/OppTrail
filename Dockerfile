FROM node:22-trixie-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS backend-base

ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libharfbuzz-subset0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --home-dir /app --no-create-home \
        --shell /usr/sbin/nologin app

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./

# CI's "backend suite inside the image" step (docs/ROADMAP.md Phase 1, review
# blocker B4): same Debian base and pinned WeasyPrint libraries as the shipped
# image, so a PDF regression that only reproduces under the real native
# libraries is caught here rather than on whatever the CI runner happens to
# have installed. Not part of the `final` stage below, so pytest and the dev
# dependency group never ship in the runtime image.
#
# Runs as the same non-root `app` user as `final` (ADR 0011 item 5, pulled
# forward from R.4 by the phase-1 review: a root container hid a real
# permission bug from `/api/health`'s writability probe -- see
# tests/test_health.py and docs/autopilot/reviews/phase-1-review-1.md). `uv
# sync`/`COPY` still run as root during the build; the `chown` below is what
# makes the venv and app tree writable (coverage output included) by the user
# the `CMD` actually runs as.
FROM backend-base AS backend-test
# `uv run` below writes a cache under $HOME (/app for the `app` user), which is
# root-owned; without this the CMD dies on "failed to create directory
# /app/.cache/uv: Permission denied". Matching the --no-cache the sync steps
# already use is simpler than carving out a writable cache directory for a
# container that runs one command and exits.
ENV UV_NO_CACHE=1
RUN uv sync --locked --no-cache
COPY backend ./
RUN chown -R app:app /app/backend
USER app
CMD ["uv", "run", "pytest", "-q", "--cov=app", "--cov-branch", "--cov-report=term-missing", "--cov-fail-under=90"]

FROM backend-base AS final

ENV DATABASE_URL=sqlite:////data/app.db \
    FRONTEND_STATIC_DIR=/app/frontend-out

RUN uv sync --locked --no-dev --no-cache

COPY backend ./
COPY --from=frontend-builder /app/frontend/out /app/frontend-out

# The process needs write access only to /data (ADR 0011 item 5): that is
# where `initialize_database()` creates the SQLite file, WAL/SHM sidecars and
# `make backup`'s snapshots. Built here so a container started with no bind
# mount (CI's `make docker-smoke`, `scripts/autopilot-gate.sh`) still has a
# writable `/data`; a real deployment bind-mounts `./data` over it, and the
# host directory must already be writable by uid 1000 -- see
# scripts/start_linux.sh / start_mac.sh, which create it with that in mind.
RUN mkdir -p /data \
    && chown -R app:app /app/backend /app/frontend-out /data

USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
