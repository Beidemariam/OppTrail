FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS backend-base

ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libharfbuzz-subset0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./

# CI's "backend suite inside the image" step (docs/ROADMAP.md Phase 1, review
# blocker B4): same Debian base and pinned WeasyPrint libraries as the shipped
# image, so a PDF regression that only reproduces under the real native
# libraries is caught here rather than on whatever the CI runner happens to
# have installed. Not part of the `final` stage below, so pytest and the dev
# dependency group never ship in the runtime image.
FROM backend-base AS backend-test
RUN uv sync --locked --no-cache
COPY backend ./
CMD ["uv", "run", "pytest", "-q", "--cov=app", "--cov-branch", "--cov-report=term-missing", "--cov-fail-under=90"]

FROM backend-base AS final

ENV DATABASE_URL=sqlite:////data/app.db \
    FRONTEND_STATIC_DIR=/app/frontend-out

RUN uv sync --locked --no-dev --no-cache

COPY backend ./
COPY --from=frontend-builder /app/frontend/out /app/frontend-out

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
