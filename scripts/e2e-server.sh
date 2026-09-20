#!/usr/bin/env bash
# Serves the real application for the Playwright suite (brief §6.1: "E2E:
# Playwright against the production build served by FastAPI").
#
# One process, one origin: FastAPI serves both /api/* and the statically
# exported frontend, exactly as the container does. `next dev` cannot be used
# here — `output: "export"` has no rewrites, so the dev server cannot reach the
# API at all (CLAUDE.md, "Dev loop gotcha").
#
# The database is rebuilt and reseeded on every start, so the suite gets the
# same fixture every run and never inherits a previous run's writes.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${E2E_PORT:-8123}"
DB_DIR="${E2E_DB_DIR:-$(pwd)/.e2e}"
DB_PATH="${DB_DIR}/e2e.db"

mkdir -p "$DB_DIR"
rm -f "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm"

export DATABASE_URL="sqlite:///${DB_PATH}"
export ENVIRONMENT=development
# The E2E run must never reach a paid API (brief §9). Leaving the key unset is
# what makes that structural: the AI endpoint answers 503 and the suite asserts
# the UI's failure state rather than a model's words.
export OPENAI_API_KEY=""
# Every Playwright test signs in from the same address, and the suite as a
# whole does that far more often in five minutes than the shipped limit of 20
# allows a real person to. Raised here only, so the suite's own volume cannot
# fail a test that is about something else; the limit itself is asserted in
# `backend/tests/test_rate_limit.py`, against the real default.
export AUTH_RATE_LIMIT_ATTEMPTS=200

cd backend
uv run python -m tools.seed >/dev/null
exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
