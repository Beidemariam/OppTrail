.PHONY: dev test test-host check check-fast e2e build docker docker-test docker-smoke seed migrate reindex frontend-deps generate-client

# Guards frontend targets against a clean checkout / empty node_modules volume
# (see docs/autopilot/DECISIONS.md's F.2 review note — the sandbox gives the
# container its own node_modules volume, which starts empty).
# npm writes node_modules/.package-lock.json on every install, so it is a
# reliable stamp for "this tree matches the lockfile". The old guard only
# checked that node_modules existed, so a lockfile change never triggered a
# reinstall: after F.7 added vitest and rollup inside the sandbox, a host that
# already had node_modules kept a tree with neither, and `npm test` failed
# there with a missing @rollup/rollup-darwin-arm64.
frontend/node_modules/.package-lock.json: frontend/package-lock.json
	cd frontend && npm ci

frontend-deps: frontend/node_modules/.package-lock.json

# Backend-only: the frontend can't reach /api/* via `next dev` (no rewrites in
# `output: "export"` mode — see CLAUDE.md's "Dev loop gotcha"). Build once and
# serve both from FastAPI.
dev: frontend-deps
	cd frontend && npm run build
	cd backend && uv run uvicorn app.main:app --reload

test:
	cd backend && uv run pytest -q

# Both halves of the split gate otherwise run the suites only under Linux -- the
# sandbox container. Nothing exercised them on the reviewer's own platform, so a
# host-only failure reached the human instead of failing a gate (F.7's
# WeasyPrint case). `scripts/autopilot-gate.sh` runs this there. D-030(a).
test-host: frontend-deps
	$(MAKE) test
	cd frontend && npm test

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
	cd frontend && npx prettier . --check
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
	@echo "Docker build + in-image backend suite + smoke test: deferred to the host —"
	@echo "this sandbox has no Docker socket (sandbox/README.md). Run"
	@echo "scripts/autopilot-gate.sh <phase>, which builds the image from the phase"
	@echo "branch and runs scripts/docker-smoke.sh against it; 'make docker-test' runs"
	@echo "the backend suite inside the image. GitHub Actions (.github/workflows/ci.yml)"
	@echo "runs both on every push."

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

# ROADMAP.md Phase 1's "backend suite inside the image": builds the
# `backend-test` Dockerfile stage (same Debian base and pinned WeasyPrint
# libraries as the shipped image, but with dev dependencies) and runs the
# suite inside it.
docker-test:
	docker build --target backend-test -t opptrail-test .
	docker run --rm opptrail-test

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

# Rebuilds the FTS5 search index from the source tables (ADR 0007). Triggers
# keep it current, so this is for a corrupted index or a tokenizer change.
reindex:
	cd backend && uv run python -m tools.reindex
