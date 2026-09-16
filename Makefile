.PHONY: dev test check check-fast e2e build docker seed migrate

# Backend-only: the frontend can't reach /api/* via `next dev` (no rewrites in
# `output: "export"` mode — see CLAUDE.md's "Dev loop gotcha"). Build once and
# serve both from FastAPI.
dev:
	cd frontend && npm run build
	cd backend && uv run uvicorn app.main:app --reload

test:
	cd backend && uv run pytest -q

# Everything that can run in this sandbox (no Docker socket — see
# sandbox/README.md). Mirrors `check` minus E2E, Docker, and audits.
check-fast:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd backend && uv run mypy app
	cd frontend && npm run typecheck
	cd frontend && npm run lint
	cd backend && uv run pytest -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90

# The full brief §3.4 gate. Pieces whose infrastructure doesn't exist yet
# (frontend unit tests, migration tests, OpenAPI contract check, E2E) print
# that they're deferred to their owning milestone rather than being silently
# absent, per the same split-gate discipline used for Docker.
check: check-fast
	cd backend && uv run pip-audit
	cd frontend && npm audit
	@echo "Frontend unit/component tests: deferred to milestone F.7 (no Vitest config yet)."
	@echo "Migration tests: deferred to milestone F.4 (no Alembic yet)."
	@echo "OpenAPI contract check: deferred to milestone F.3 (no generated client yet)."
	@$(MAKE) e2e
	@echo "Docker build + smoke test: deferred to the host — this sandbox has no"
	@echo "Docker socket (sandbox/README.md). Run scripts/autopilot-gate.sh <phase>."

e2e:
	@echo "Playwright E2E: deferred to milestone F.7 (no Playwright config yet)."

build:
	cd frontend && npm run build

docker:
	docker build -t opptrail .

seed:
	@echo "Seed data script: deferred to milestone F.7."

migrate:
	@echo "Migrations: deferred to milestone F.4 (Alembic not yet introduced;"
	@echo "database.py's run_migrations() currently runs automatically on startup)."
