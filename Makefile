.PHONY: dev test check check-fast e2e build docker seed migrate frontend-deps generate-client

# Guards frontend targets against a clean checkout / empty node_modules volume
# (see docs/autopilot/DECISIONS.md's F.2 review note — the sandbox gives the
# container its own node_modules volume, which starts empty).
frontend-deps:
	cd frontend && [ -d node_modules/.bin ] || npm ci

# Backend-only: the frontend can't reach /api/* via `next dev` (no rewrites in
# `output: "export"` mode — see CLAUDE.md's "Dev loop gotcha"). Build once and
# serve both from FastAPI.
dev: frontend-deps
	cd frontend && npm run build
	cd backend && uv run uvicorn app.main:app --reload

test:
	cd backend && uv run pytest -q

# Regenerates frontend/lib/api-types.ts from the live OpenAPI schema.
generate-client: frontend-deps
	./scripts/generate-api-client.sh

# Everything that can run in this sandbox (no Docker socket — see
# sandbox/README.md). Mirrors `check` minus E2E, Docker, and audits.
check-fast: frontend-deps
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd backend && uv run mypy app
	cd frontend && npm run typecheck
	cd frontend && npm run lint
	cd backend && uv run pytest -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90
	./scripts/generate-api-client.sh --check

# The full brief §3.4 gate. Pieces whose infrastructure doesn't exist yet
# (frontend unit tests, migration tests, E2E) print that they're deferred to
# their owning milestone rather than being silently absent, per the same
# split-gate discipline used for Docker.
check: check-fast
	cd backend && uv run pip-audit
	cd frontend && npm audit
	@echo "Frontend unit/component tests: deferred to milestone F.7 (no Vitest config yet)."
	@$(MAKE) e2e
	@echo "Docker build + smoke test: deferred to the host — this sandbox has no"
	@echo "Docker socket (sandbox/README.md). Run scripts/autopilot-gate.sh <phase>."

e2e:
	@echo "Playwright E2E: deferred to milestone F.7 (no Playwright config yet)."

build: frontend-deps
	cd frontend && npm run build

docker:
	docker build -t opptrail .

seed:
	@echo "Seed data script: deferred to milestone F.7."

# The application also runs this on startup, so a normal boot needs no manual
# step; this target is for inspecting or applying revisions by hand.
migrate:
	cd backend && uv run alembic upgrade head
