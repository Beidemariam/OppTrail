.PHONY: dev test check check-fast e2e build docker docker-smoke seed migrate frontend-deps generate-client

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
	cd backend && uv run mypy app tools
	cd frontend && npm run typecheck
	cd frontend && npm run lint
	cd backend && uv run pytest -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90
	cd frontend && npm run test:coverage
	./scripts/generate-api-client.sh --check

# The full brief §3.4 gate. Every item runs here except the last, which needs a
# Docker socket this sandbox deliberately does not have (sandbox/README.md);
# that half is named rather than silently skipped, per the split gate.
check: check-fast
	cd backend && uv run pip-audit
	cd frontend && npm audit
	@$(MAKE) e2e
	@echo
	@echo "Docker build + smoke test: deferred to the host — this sandbox has no"
	@echo "Docker socket (sandbox/README.md). Run scripts/autopilot-gate.sh <phase>,"
	@echo "which builds the image from the phase branch and runs scripts/docker-smoke.sh"
	@echo "against it."

# Playwright builds the frontend and starts scripts/e2e-server.sh itself (see
# frontend/playwright.config.ts), so this needs no separate build step.
# The browser binary is version-specific and not baked into any image, so it is
# fetched on demand into PLAYWRIGHT_BROWSERS_PATH; the system libraries it needs
# are already present (sandbox/README.md). Re-running this is a no-op.
e2e: frontend-deps
	cd frontend && npx playwright install chromium
	cd frontend && npm run e2e

build: frontend-deps
	cd frontend && npm run build

docker:
	docker build -t opptrail .

# Small, fast demo data covering every shipped feature and permission
# relationship. Prints the seeded users and what each of them can see.
seed:
	cd backend && uv run python -m tools.seed

# The host half of the gate. Needs a Docker socket, so it cannot run in the
# autopilot sandbox; scripts/autopilot-gate.sh calls the same script.
docker-smoke: docker
	./scripts/docker-smoke.sh opptrail

# The application also runs this on startup, so a normal boot needs no manual
# step; this target is for inspecting or applying revisions by hand.
migrate:
	cd backend && uv run alembic upgrade head
