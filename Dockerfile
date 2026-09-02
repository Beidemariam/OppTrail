FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV DATABASE_URL=sqlite:////data/app.db \
    FRONTEND_STATIC_DIR=/app/frontend-out \
    PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-cache

COPY backend ./
COPY --from=frontend-builder /app/frontend/out /app/frontend-out

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
