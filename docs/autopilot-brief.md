# OppTrail Autopilot Brief — Phase-Gated

## 0. Mission and how this run is structured

Take OppTrail from its accepted MVP to a production-grade, fully tested, documented, deployable v2 — ClickUp-caliber depth **within sales opportunity tracking only**.

The work is divided into gated phases, executed in this order:

| Phase ID | Name | Source of scope |
|---|---|---|
| `F` | Foundations: reconnaissance, hardening, test infrastructure | §4 of this brief |
| `1`–`6` | Roadmap Phases 1–6 | `docs/ROADMAP.md` (authoritative) |
| `R` | Release readiness: operations, performance, documentation | §8 of this brief |

The MVP's historical "Phase 0" is complete and accepted. Do not redo it. The phase IDs above are the only ones this brief uses.

Each phase runs on its own branch, ends at a green quality gate, and stops for human review. **Nothing reaches `main` except through the human Accept step.**

**Stack (change only via an accepted ADR):** Next.js + TypeScript (App Router) · Python FastAPI (also serves the static frontend) · SQLite · session auth with bcrypt and HttpOnly cookies · OpenRouter-backed read-only AI agent · WeasyPrint PDF export · single Docker container with `uv`.

---

## 1. Source-of-truth hierarchy

Read everything below that exists before acting. Higher items win conflicts; record every conflict and its resolution in `docs/autopilot/DECISIONS.md`.

1. The actual code and tests
2. `AGENTS.md` (including its Autopilot section) and `PLAN.md`
3. ADRs
4. `docs/ROADMAP.md`
5. `docs/v2-review-brief.md` and the planning outputs it produced
6. This brief

Known stale item: `docs/v2-review-brief.md` references the model `gpt-oss-20b`, which contradicts the code and ADRs. Code/ADRs are correct. Fix the reference during Phase F.

Any claim about existing code in a planning or review document must cite a file path. Do not describe code you have not opened.

---

## 2. Invariants — never violate

Each has a dedicated test (§6.4).

1. **The AI agent is read-only by construction** — no write tools registered, and its data access physically cannot mutate state. Instruction-only restrictions are not acceptable.
2. **Comments are immutable** after posting.
3. **Notes are editable** with an edit marker (and full revision history once built).
4. **Soft deletes everywhere.** No hard deletes of user data in application code paths.
5. **Event timestamps are editable; `created_at` is immutable.**
6. **Sales stages are a fixed, non-renamable list.**
7. **Viewer/editor sharing is enforced server-side** on every endpoint.
8. **Domain narrowness.** No CRM contact/account databases, lead scoring, outbound email pipelines, general project management, billing, or SSO. Scope drift gets logged as a non-goal, not built.

---

## 3. Operating model

### 3.1 Git and the phase gate
- **Starting a phase:** verify the previous phase's tag `phase-<prev>-accepted` exists (not needed for `F`). Check out `main`, pull nothing, and create `autopilot/phase-<ID>` from `main`. If the branch already exists, check it out and resume.
- **During a phase:** commit each completed milestone to `autopilot/phase-<ID>` using Conventional Commits. Commits on autopilot branches are permitted by `AGENTS.md`'s Autopilot section; commits to `main` are not.
- **You must never:** commit to `main`, merge or rebase into `main`, create or delete `phase-*-accepted` tags, push to any remote, force-push, rewrite history, or use `--no-verify`. The human runs `scripts/autopilot-accept.sh`, which fast-forwards `main` and tags acceptance.
- **Ending a phase:** when every milestone in the phase is done and the full gate (§3.4) is green, write the review packet (§3.5), set the status to `AWAITING_REVIEW`, commit, and **stop. Do not begin the next phase.**

### 3.2 State files (`docs/autopilot/`, committed on the phase branch)
- `PROGRESS.md` — first line is exactly one of:
  - `STATUS: IN_PROGRESS phase=<ID>`
  - `STATUS: AWAITING_REVIEW phase=<ID>`
  - `STATUS: REWORK phase=<ID>`
  - `STATUS: BLOCKED phase=<ID>`

  Below it: every phase and milestone with checkboxes, acceptance criteria, and a short work log. It must always be accurate enough for a fresh session to resume using only this brief and the state files.
- `DECISIONS.md` — `D-### | date | question | options | choice | reason | reversible (Y/N) | needs human review (Y/N)`.
- `BLOCKERS.md` — unresolvable issues with what was tried.
- `COVERAGE.md` — coverage per milestone, so regressions are visible.
- `reviews/` — review packets and human feedback files.

### 3.3 Session discipline
Your context will not hold the whole project. Each session does this:
1. Read this brief and all state files. Read any unaddressed file in `docs/autopilot/reviews/` whose decision is REJECT.
2. Determine the current state from `PROGRESS.md`'s first line and git tags:
   - No `PROGRESS.md` → start Phase F.
   - `IN_PROGRESS` → resume the next unfinished milestone.
   - `REWORK` → address every item in the latest rejection feedback for that phase first, then re-run the gate.
   - `AWAITING_REVIEW` and the matching `phase-<ID>-accepted` tag exists → start the next phase per §0's order (for `R`, the project is finished; stop).
   - `AWAITING_REVIEW` without the tag → do nothing and exit. The human hasn't reviewed yet.
   - `BLOCKED` → re-check whether the blocker is resolved; if not, exit.
3. Complete **one** milestone to a green gate, update state files, commit, and exit.

No clarifying questions — nobody answers during a phase. Choose the option most consistent with §1–§2, log it in DECISIONS.md, and mark `needs human review: Y` if it's architectural, non-reversible, or expands scope. These are surfaced at the gate.

If the same failure repeats three times with no new information, log it in BLOCKERS.md and move to the next independent milestone. Set `BLOCKED` only when no milestone in the phase can proceed.

### 3.4 Quality gate
`make check` (create it in Phase F) runs:
- `ruff check`, `ruff format --check`, strict `mypy` or `pyright`
- `eslint`, strict `tsc --noEmit`, `prettier --check`
- Backend unit + integration tests with enforced coverage thresholds
- Frontend unit/component tests with enforced thresholds
- Migration tests
- OpenAPI contract check (generated TS client is current)
- Playwright E2E with axe accessibility checks
- `pip-audit` and `npm audit` (no high/critical)
- Docker build + smoke test

`make check-fast` may skip E2E, Docker, and audits during inner-loop work. **Milestone commits require `make check-fast`; `AWAITING_REVIEW` requires full `make check`.**

### 3.5 Review packet
At the end of each phase, write `docs/autopilot/reviews/phase-<ID>-summary.md`, designed for a human to review in 20–30 minutes:
1. **What changed** — features and fixes in plain language, mapped to roadmap items
2. **How to try it** — exact commands, seeded users, and a click-path for each new capability
3. **Decisions needing review** — every `needs human review: Y` entry from this phase, with the recommended choice and its alternative
4. **Quality evidence** — `make check` result, coverage vs. previous phase, new invariant/E2E tests
5. **Risks and known limitations**
6. **Out-of-scope items noticed** — logged, not built
7. **Preview of next phase** — first milestones and any decision that should be settled before starting

---

## 4. Phase F — Foundations

Branch: `autopilot/phase-F`. No new user-facing features in this phase.

### 4.1 Reconnaissance
1. Inventory: directory map, full data model, every API route with its permission behavior, every frontend route, existing tests, environment variables. Write `docs/autopilot/INVENTORY.md` with file citations.
2. Run the app and existing tests; record baseline results and coverage. Do not weaken failing tests.
3. Read `docs/ROADMAP.md` fully. Convert Phases 1–6 into milestone lists in `PROGRESS.md`, preserving roadmap wording and order. Split large items into milestones small enough to finish in one session.
4. **Scope cross-check.** Compare the roadmap with the capability list in §7. For anything in §7 not covered by the roadmap, add a `needs human review: Y` proposal to DECISIONS.md with a suggested phase. **Do not add it to the plan** — the human accepts or rejects it at the Phase F gate.
5. Gap analysis: security weaknesses, correctness issues, missing tests, and any existing violation of §2. Each becomes a Phase F milestone.
6. Fix the stale `gpt-oss-20b` reference.

### 4.2 Tooling and structure
- `Makefile`: `dev`, `test`, `check`, `check-fast`, `e2e`, `build`, `docker`, `seed`, `migrate`.
- Pre-commit hooks mirroring `check-fast`.
- Clear layering: routers (HTTP only) → services (business rules and permission checks) → data access.
- Typed settings with fail-fast validation; `.env.example` documents every variable.
- Structured JSON logging with request IDs; no secrets or tokens in logs.
- Consistent API error envelope; no stack traces to clients in production mode.

### 4.3 API contract
- Every endpoint has typed request/response models in OpenAPI.
- Generate TypeScript types/client from the schema; no hand-written API types.
- Gate fails on a stale generated client.

### 4.4 Database
- Versioned migrations (Alembic) with the current schema as baseline; run migrations at startup, preserving zero-setup for new installs.
- SQLite WAL, foreign keys on, busy timeout set.
- ADR (`needs human review: Y`): SQLite fitness for v2 given real-time features and a single container. Default recommendation is SQLite with WAL, with data access kept portable. No database migration without an accepted ADR.
- Central soft-delete implementation with a test that fails on hard deletes of user data.

### 4.5 Security
- CSRF protection for cookie sessions; secure cookie flags; session rotation on login, invalidation on logout and password change.
- Rate limiting on login/signup; generic auth errors.
- One central permission-check function used by every service method touching an opportunity.
- Upload hardening: size limits, content sniffing, randomized stored names, safe paths, forced download disposition, traversal tests.
- Server-side sanitization framework for any user HTML (ready for rich text).
- Security headers (CSP, X-Content-Type-Options, Referrer-Policy, frame-ancestors).

### 4.6 AI agent
- Read-only DB access plus zero write tools, both asserted by tests.
- Agent inherits the requesting user's permissions; cross-opportunity leakage tests.
- Prompt-injection tests using hostile content in notes and attachments.
- Single OpenRouter client wrapper with timeouts, retries, and graceful failure; always mocked in tests.

### 4.7 Test infrastructure
Stand up every layer in §6, the authorization matrix, the invariant tests, seed data, and the Docker smoke test, so Phases 1–6 only add tests rather than build infrastructure.

---

## 5. Phases 1–6 — Roadmap execution

Branches: `autopilot/phase-1` … `autopilot/phase-6`.

- `docs/ROADMAP.md` defines the scope of each phase, plus any proposals the human accepted at earlier gates (recorded in DECISIONS.md or review feedback).
- Do not pull work forward from later phases or add unaccepted scope.
- Write an ADR before any architectural change (e.g. the real-time transport, notification delivery, search indexing approach). Mark it `needs human review: Y`.
- Every feature milestone includes: migration → service with permission checks → API → regenerated client → frontend → unit, integration, and E2E tests → authorization-matrix entries → seed data demo path → docs.
- Every new endpoint must be registered in the authorization matrix, or the matrix test fails.
- Add each §6.3 E2E journey in the phase where its features land.

---

## 6. Testing strategy

### 6.1 Layers
- **Backend unit** (pytest): services, permissions, validators, sanitizers, rule engines.
- **Backend integration:** real FastAPI app, real SQLite with migrations applied, isolated per test.
- **Frontend unit/component:** Vitest (or the existing runner) + React Testing Library, API mocked against generated types.
- **Contract:** generated client matches the live schema; responses validate against schemas.
- **E2E:** Playwright against the production build served by FastAPI, with `@axe-core/playwright` on major pages.
- **Migration:** upgrade from empty and from an MVP-era snapshot with realistic data.
- **Docker smoke:** build, start, health check, log in as a seeded user, open an opportunity, export a PDF.
- **Performance (Phase R):** large seeded dataset; key endpoints within documented latency budgets; query-count tests against N+1 regressions.

### 6.2 Coverage floors (never lowered)
- Backend ≥ 90% line, ≥ 80% branch.
- Auth, permissions, soft delete, audit, and AI agent modules ≥ 95% branch.
- Frontend ≥ 80% line.
- Coverage is a floor; tests must assert behavior.

### 6.3 Critical E2E journeys (each added when its features exist; all present by Phase R)
1. Sign up → create opportunity → add typed entries → change stage → system entry appears.
2. Share as viewer (read-only verified) → upgrade to editor (can edit notes, cannot edit comments).
3. Edit note → edit marker → revision history.
4. Attach file → download → soft delete → hidden in UI, retained in audit.
5. @mention → recipient notified.
6. Search finds opportunities and entries the user can access, and nothing else.
7. Custom field → filter view → save view → persists on reload.
8. Board view stage drag → system entry.
9. Stalled flag → reminder notification.
10. Automation triggers on stage change.
11. CSV/JSON/PDF export respects permissions.
12. AI agent answers on accessible data; refuses and leaks nothing on inaccessible data.
13. Keyboard-only: command palette → opportunity → add note.

Drop or adapt any journey whose feature the roadmap and accepted decisions do not include, and note it in the review packet.

### 6.4 Invariant tests (`test_invariant_*`)
- AI agent: no write tools; write through its data layer fails.
- No comment edit route (PATCH/PUT → 404/405).
- Hard-delete detection.
- `created_at` immutable via every endpoint.
- Stage list cannot be renamed or extended.
- **Authorization matrix:** every endpoint × {owner, editor, viewer, unrelated user, anonymous}; unregistered routes fail the test.

### 6.5 Hygiene
- No live network in tests; a guard fails any real outbound HTTP.
- Deterministic time and randomness; no order dependence.
- No blind retries, sleeps, skips, or xfails to reach green. Quarantined tests go in BLOCKERS.md and count as unfinished.
- Never change an assertion to make broken code pass. If an expectation is genuinely wrong, justify it in the commit and DECISIONS.md.

---

## 7. Capability reference (for the Phase F scope cross-check only)

This is the ClickUp-caliber target. It is **not** a build list. The roadmap and accepted decisions are.

System-generated timeline entries · entry type tags with color/icon · note edit history · audit log · @mentions and in-app notifications · stalled-opportunity flags and follow-up reminders · CSV/JSON export (PDF retained) · rich text · custom fields · table/board/calendar views · saved and shareable filtered views · dashboards (pipeline, value by stage, stalled, activity, my follow-ups) · real-time collaboration · opportunity-scoped automations (trigger → condition → action, each action logged) · keyboard-first navigation and command palette · design system with light/dark themes · WCAG 2.1 AA.

---

## 8. Phase R — Release readiness

Branch: `autopilot/phase-R`.

- **UX consistency:** loading, empty, and error states everywhere; responsive to tablet; timeline usable on mobile; design tokens applied consistently.
- **Accessibility:** axe clean; focus management in dialogs and palette; full keyboard operability.
- **Performance:** large-dataset budgets met; list/timeline virtualization; indexes justified by measurement.
- **Docker:** multi-stage build, non-root user, pinned versions, WeasyPrint dependencies, `HEALTHCHECK`, `/healthz` and `/readyz`, graceful shutdown.
- **Data safety:** documented volume layout; SQLite online backup and restore procedure with a restore test; uploads included.
- **CI:** GitHub Actions running `make check` on push to `main`, with coverage and Playwright report artifacts and an image build. (Create the workflow file; you do not push it.)
- **Seed data** exercising every shipped feature and permission relationship.
- **Documentation:** `README.md`, `ARCHITECTURE.md` (Mermaid data model, auth/permission model, real-time design, AI read-only guarantee), ADR index, API guide, `docs/user-guide.md`, `docs/operations.md`, `CHANGELOG.md`, updated `AGENTS.md` and `PLAN.md`.
- **Final report:** `docs/autopilot/FINAL-REPORT.md` — what shipped per phase, coverage history, invariant and E2E test lists, open blockers, non-reversible decisions, recommended next steps.

The Phase R review packet doubles as the release sign-off.

---

## 9. Guardrails

Never:
- Touch anything outside the repository.
- Read, print, or commit secrets; `.env*` (except `.env.example`) stays ignored. Log any committed secret in BLOCKERS.md; do not rewrite history.
- Call OpenRouter or any paid external API.
- Delete `.git`, tags, user data, or anything you didn't create.
- Weaken tests, linters, type checks, audits, or coverage floors.
- Commit to `main`, merge, tag acceptance, push, force-push, rewrite history, or use `--no-verify`.
- Install from unofficial sources or pipe downloaded scripts to a shell.
- Change the stack or expand scope without an accepted decision.
- Start a new phase without its predecessor's acceptance tag.
- Mark a milestone done with a red gate.

---

## 10. Definition of Done (project)

- [ ] `phase-F-accepted` through `phase-6-accepted` and `phase-R-accepted` tags exist
- [ ] `make check` green on `main` from a clean clone
- [ ] Coverage floors met; history in COVERAGE.md
- [ ] Invariant tests and authorization matrix passing
- [ ] All applicable E2E journeys passing with axe checks
- [ ] Docker image passes smoke test, runs non-root; backup/restore tested
- [ ] CI workflow present and valid
- [ ] No unresolved high/critical dependency vulnerabilities
- [ ] Documentation set and FINAL-REPORT.md complete