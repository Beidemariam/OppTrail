# Phase F — Inventory

Reconnaissance snapshot taken at the start of autopilot Phase F, branch
`autopilot/phase-F`, base commit `4c16a70` (`main`). Every claim below cites the
file it was read from, per brief §1.

## 1. Directory map

```
backend/
  app/                  FastAPI application (see §3 below), 3,243 lines across 19 files
  tests/                pytest suite, one file per router/concern (see §5)
  pyproject.toml        deps: fastapi, openai, passlib[bcrypt] (bcrypt<5 pinned),
                         pydantic-settings, uvicorn, weasyprint; dev: httpx, pytest,
                         pytest-cov. No ruff/mypy/black in the dep list.
frontend/
  app/page.tsx          the entire application, 1,829 lines, one "use client" component
  app/layout.tsx, globals.css
  package.json          next/react/react-dom/typescript/eslint pinned to "latest";
                         react-markdown + rehype-sanitize + remark-gfm for rich text render
  no test runner configured (`backend/tests` has 34 tests; frontend has none)
docs/                   AGENTS.md-referenced planning set: PLAN.md, REVIEW.md, FEATURES.md,
                         ARCHITECTURE.md, adr/0001-0012, DESIGN-SYSTEM.md, UX.md,
                         ROADMAP.md, OPEN-QUESTIONS.md, TEST_CRITERIA.md, code_review.md,
                         v2_review_brief.md, autopilot-brief.md
scripts/                start/stop scripts (mac/linux/windows) + autopilot.sh,
                         autopilot-accept.sh, autopilot-gate.sh, autopilot-reject.sh
sandbox/                the containment environment this session runs in (README.md,
                         run.sh, proxy/) — not part of the shipped product
Dockerfile              present at repo root; no Makefile, no .github/ (CI does not exist yet)
.env.example            DATABASE_URL, FRONTEND_STATIC_DIR, OPENAI_API_KEY, OPENAI_MODEL,
                         SESSION_SECRET
```

No Makefile, no `.github/`, no `alembic/`, no `.pre-commit-config.yaml` exist yet —
all of §4.2's tooling is genuinely new work, not misconfigured existing work.

## 2. Environment variables

Read from `backend/app/settings.py:4-11` (the only settings module) and
`.env.example`:

| Variable | Default | Used at |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./app.db` | `database.py:9-14` — must be `sqlite:///`-prefixed, enforced by a `ValueError`, not a Pydantic validator |
| `FRONTEND_STATIC_DIR` | `../frontend/out` | `main.py:40-41`, mounted for `/_next` and the SPA fallback |
| `OPENAI_API_KEY` | `None` | `routes_ai.py:26` — 503 if unset |
| `OPENAI_MODEL` | `gpt-5.6-luna` | `routes_ai.py:39`, passed to `ai_service.ask_openai` |
| `SESSION_SECRET` | `dev-only-change-me` | declared, **never read anywhere** (dead config — `code_review.md` finding 10) |

`Settings` (`settings.py:4-11`) has no `field_validator`s and no fail-fast checks
beyond Pydantic's own type coercion — e.g. a malformed `DATABASE_URL` is only
caught later, inside `sqlite_path_from_url` (`database.py:9-14`), not at process
start. This is exactly the "typed settings with fail-fast validation" gap named
in brief §4.2.

## 3. Backend: data model

`backend/app/schema.sql` (read in full). All tables use
`CREATE TABLE IF NOT EXISTS`; there is no migrations directory or version table —
`database.py:55-71` (`run_migrations`) applies two additive `ALTER TABLE`s guarded
by `column_exists()` (`database.py:46-52`), then `normalize_legacy_timestamps`
(`database.py:92-104`) and `backfill_opportunity_created_entries`
(`database.py:107-140`), all idempotent and re-run on every startup.

| Table | Key columns | Notes |
|---|---|---|
| `users` | `email` UNIQUE, `password_hash`, `name` | no `updated_at`, no soft delete (users are never deleted) |
| `sessions` | `id` (opaque token), `user_id`, `expires_at` | hard-deleted on logout (`auth.py:48-54`) — sessions are not user data on the invariant's terms, but nothing purges expired rows (`code_review.md` finding 10) |
| `opportunities` | `stage` CHECK-constrained to the 7 fixed stages, `owner_id`, `deleted_at` | stage list is enforced at the schema level, satisfying invariant §2.6 structurally |
| `opportunity_shares` | `(opportunity_id, user_id)` UNIQUE, `role` CHECK IN ('viewer','editor'), `deleted_at` | re-sharing after a soft-deleted share un-deletes the row rather than inserting a duplicate (`routes_sharing.py:114-125`) |
| `timeline_entries` | `type` CHECK-constrained (8 values), `event_timestamp`, `follow_up_date`, `system_generated`, `created_at`, `deleted_at` | no `updated_at` — entries are not editable in the general case except via the fields `TimelineEntryUpdate` exposes |
| `notes` | `body`, `edited`, `updated_at`, `deleted_at` | full history in `note_versions`, not just an `edited` flag |
| `note_versions` | `(note_id, version_number)` UNIQUE | append-only; row 1 is written at note creation (`routes_timeline.py:475-481`) |
| `comments` | `body`, `created_at`, `deleted_at` | **no `updated_at`, no update route** — comments are immutable after posting by construction (invariant §2.2), not by convention |
| `notifications` | `type`, `payload` (JSON text), `read` | no `read_at` timestamp, no `grouped_key` — matches ROADMAP.md Phase 1's planned schema addition |
| `audit_log_entries` | `actor_id`, `action`, `detail` (JSON text) | owner-only forensics, separate from `timeline_entries` |

Indexes: owner_id, session user_id/expires_at, share user_id, entry opportunity_id,
note entry_id, comment note_id, notification user_id, audit opportunity_id
(`schema.sql`, final block). No index on `(opportunity_id, event_timestamp)`
despite every timeline read ordering by it — a candidate for the Phase F/R
performance pass, not urgent at current seeded scale.

## 4. Backend: API surface and permission behavior

Routers mounted in `main.py:26-32`. Every route depends on
`get_current_user` (`auth.py:57-84`, session cookie → row lookup, 401 if missing
or expired) except signup/login (`routes_auth.py:30-73`) and `/api/health`
(`main.py:35-37`, unauthenticated by design).

| Method & path | File:line | Permission call | Behavior notes |
|---|---|---|---|
| `POST /api/auth/signup` | `routes_auth.py:30` | none (creates the session) | 409 on duplicate email |
| `POST /api/auth/login` | `routes_auth.py:58` | none | generic "Invalid email or password" on both bad email and bad password |
| `POST /api/auth/logout` | `routes_auth.py:76` | none (session-token based) | hard-deletes the session row — not opportunity data, not a soft-delete violation |
| `GET /api/auth/me` | `routes_auth.py:85` | `get_current_user` | |
| `GET /api/opportunities` | `routes_opportunities.py:135` | inline `WHERE owner_id = ? OR shares.user_id = ?` | does not call `permissions.py` — see finding below |
| `POST /api/opportunities` | `routes_opportunities.py:172` | none beyond auth (creation is unconditional) | writes the "Opportunity created" system entry |
| `GET /api/opportunities/{id}` | `routes_opportunities.py:217` | `fetch_accessible_opportunity` (inline query, same shape as `permissions.get_opportunity_role`) | 404 on no access |
| `PATCH /api/opportunities/{id}` | `routes_opportunities.py:234` | `fetch_owned_opportunity` (inline, owner-only) | **does not use `permissions.require_opportunity_owner`**; duplicates its logic ad hoc |
| `DELETE /api/opportunities/{id}` | `routes_opportunities.py:289` | `fetch_owned_opportunity` (inline, owner-only) | same duplication; cascades soft-delete through shares → entries → notes → comments; audited (`opportunity_deleted`) |
| `GET /api/opportunities/{id}/shares` | `routes_sharing.py:60` | `require_opportunity_owner` | |
| `POST .../shares` | `routes_sharing.py:77` | `require_opportunity_owner` | notifies invitee; audits `share_added` |
| `PATCH .../shares/{user_id}` | `routes_sharing.py:173` | `require_opportunity_owner` | audits `share_role_changed`, only if role actually changes |
| `DELETE .../shares/{user_id}` | `routes_sharing.py:247` | `require_opportunity_owner` | audits `share_removed` |
| `GET .../audit-log` | `routes_sharing.py:312` | `require_opportunity_owner` | owner-only forensics, per invariant |
| `GET .../timeline` | `routes_timeline.py:138` | `require_opportunity_access` | keyword/type/date/author filters, all parameterized |
| `POST .../timeline` | `routes_timeline.py:286` | `require_timeline_write` | notifies shared users |
| `PATCH /api/timeline/{id}` | `routes_timeline.py:340` | `require_timeline_write` + explicit `system_generated` guard | any editor may edit any colleague's entry (no author check) — see permissions note below |
| `DELETE /api/timeline/{id}` | `routes_timeline.py:387` | `require_delete_permission` + `system_generated` guard | audits `timeline_entry_deleted` |
| `POST /api/timeline/{id}/notes` | `routes_timeline.py:453` | `require_timeline_write` | writes `note_versions` row 1; notifies mentions + shared activity |
| `PATCH /api/notes/{id}` | `routes_timeline.py:513` | `require_timeline_write` (no author check — any editor may edit any colleague's note) | appends a new `note_versions` row |
| `GET /api/notes/{id}/versions` | `routes_timeline.py:580` | `require_opportunity_access` (read, so viewers can see it too) | |
| `DELETE /api/notes/{id}` | `routes_timeline.py:618` | `require_delete_permission` | audits `note_deleted` |
| `POST /api/notes/{id}/comments` | `routes_timeline.py:663` | `require_timeline_write` | notifies note author + mentions + shared activity |
| `DELETE /api/comments/{id}` | `routes_timeline.py:727` | `require_delete_permission` | audits `comment_deleted`; **no PATCH/PUT route exists for comments at all** — satisfies invariant §2.2 structurally |
| `POST /api/opportunities/{id}/ai/ask` | `routes_ai.py:20` | `require_opportunity_access` | 503 if no API key; 502 on any OpenAI exception (swallowed, unlogged) |
| `GET .../export/json,csv,pdf` | `routes_export.py:33,48,64` | `require_opportunity_access` (via `get_export_data`) | CSV escapes formula-injection prefixes; PDF/HTML escapes every field |
| `GET /api/notifications` | `routes_notifications.py:24` | `get_current_user` only, scoped by `user_id` in the query | **returns `WHERE read = 0` only** — read notifications vanish, not just visually; this is ROADMAP.md Phase 1's named "dead end" |
| `PATCH /api/notifications/{id}/read` | `routes_notifications.py:44` | `get_current_user`, scoped by `user_id` | 404 if the notification belongs to someone else |
| `GET /api/health` | `main.py:35` | none | |
| `GET /_next/*` | `main.py:44` | static mount | |
| `GET /{path}` (SPA fallback) | `main.py:56-69` | path resolved and checked `is_relative_to` the static root before serving | this is the fixed path-traversal hole from `code_review.md` finding 1; the fix is in place and tested (`test_static_files.py`) |

**Permission-check consolidation gap.** `permissions.py` defines
`get_opportunity_role`, `require_opportunity_access`, `require_timeline_write`,
`require_delete_permission`, `require_opportunity_owner` — but
`routes_opportunities.py`'s `fetch_accessible_opportunity` (`:86-114`) and
`fetch_owned_opportunity` (`:117-132`) re-implement the same role resolution
inline rather than calling into `permissions.py`. The net behavior is currently
correct (verified by `test_non_owner_cannot_view_or_mutate_opportunity`,
`test_opportunities.py:134`), but it is two independent implementations of "who
can touch this opportunity" that could silently diverge on a future edit. This
is exactly the risk brief §4.5 names: "One central permission-check function used
by every service method touching an opportunity." Candidate Phase F milestone.

**Author-vs-editor asymmetry (already known, resolved for delete, still open for
edit).** `code_review.md` finding 4a covered *delete*, which now uses
`require_delete_permission` uniformly. *Edit* was not part of that fix: any
editor may `PATCH` any colleague's timeline entry (`routes_timeline.py:340-383`)
or note (`:513-577`) today — `AGENTS.md`'s permissions model says "Editors add
and edit freely" without restricting edit-of-others'-content, so this is not a
defect against the current spec, but it is worth naming explicitly as a decision
already made (editors may edit anyone's content; only deletion is
author-or-owner) rather than an oversight, so a future session does not
"fix" it into an inconsistency with the tests.

## 5. Backend: existing tests

`backend/tests/` (`conftest.py` + 8 files, 34 test functions). Full list by
file, from `grep -n "^def test_"`:

- `test_auth.py` (5): signup/session, duplicate signup, login/logout, invalid
  login, protected-endpoint-without-session.
- `test_opportunities.py` (3): owner CRUD lifecycle, startup backfill of
  "Opportunity created" entries, non-owner cannot view or mutate.
- `test_sharing.py` (4): owner manages shares + audit history, shared user's
  dashboard/permissions follow role, non-owner cannot manage shares/audit,
  share validation errors.
- `test_timeline.py` (9): full CRUD + note versions, filter combinations,
  cascade soft-delete, editor-write/viewer-read-only, comment delete
  author-or-owner, editor cannot delete another's note/entry, deletions land in
  the audit log, canonical UTC timestamp storage/sorting, client timestamp
  normalization, invalid timestamps rejected without taking the dashboard down.
- `test_notifications.py` (5): mention extraction dedup, mentions/comments/
  shared-activity create notifications, user can mark only their own
  notification read, share changes notify, follow-up permission + stalled
  calculation.
- `test_export.py` (5): JSON/CSV/PDF for owner, shared users can export and
  unshared cannot, CSV neutralizes formulas, PDF HTML renders in order and
  escapes bodies, real PDF is produced (WeasyPrint-gated).
- `test_static_files.py` (2): serves files inside the build, refuses to escape
  the build directory (the path-traversal regression test).
- `test_ai.py` (5): AI answer uses context and never writes, viewer can ask but
  not write, blocked without access, helpful errors on failure, markdown-bold
  normalization.

**No test file is organized as `test_invariant_*`, and there is no
authorization-matrix test that enumerates every route against
{owner, editor, viewer, unrelated user, anonymous} and fails when a route is
unregistered.** Coverage of the underlying behavior is good (see §7), but the
brief's §6.4 structure does not exist yet — this is exactly what Phase F §4.7
asks to stand up.

Frontend: **zero tests**. No Vitest/Jest config, no Playwright config, no
`@axe-core` dependency in `package.json`.

## 6. Frontend

`frontend/app/page.tsx` (1,829 lines) is confirmed as the entire application —
one `"use client"` component, 28+ `useState` hooks (ADR 0005 cites this exact
count), no router, `apiRequest<T>()` as the sole fetch wrapper. Read directly to
confirm: `parseTimestamp`/`localInputToUtc`/`formatTimestamp` (lines 201-225,
boundary conversion), `MarkdownText` (line 256, `rehype-sanitize` with a
`defaultSchema` extension), `window.confirm`-based delete confirmation (line
229, per `code_review.md` finding 8's fix), and the full `useState` block
(lines 277-313) covering auth, opportunities, timeline, shares, audit log, AI
conversations (keyed per opportunity id), notifications, and per-item note/
comment draft state.

There is exactly one route: `/`. `next.config.ts` sets `output: "export"`, so
this is a static SPA with no server component and no `/api` rewrite — confirmed
in `CLAUDE.md` and consistent with ADR 0005's premise that a second route is
what would justify introducing a router (Phase 2).

## 7. Baseline: tests and coverage

Run inside this sandbox, `backend/`, `uv run pytest -q --cov=app
--cov-report=term-missing`:

```
39 passed in 14.62s
TOTAL: 1032 stmts, 44 miss, 96% cover
```

Per-file coverage (files below 95%, everything else 97-100%):

| File | Cover | Missing lines |
|---|---|---|
| `ai_service.py` | 82% | 32, 71, 99, 105, 130-137 (the real `ask_openai` call and a couple of edge branches in context-building) |
| `database.py` | 94% | 11, 57, 64 (a `ValueError` branch and two migration guards that only fire once per fresh DB) |
| `main.py` | 93% | 37, 53, 69 (the `_next` static mount guard and two fallback branches) |
| `routes_opportunities.py` | 92% | 64, 242-250 (the stalled-query none-branch and no-op `PATCH` with an empty body) |
| `routes_sharing.py` | 95% | 109, 115, 194, 267 (validation edge branches) |
| `routes_timeline.py` | 94% | 10 lines, mostly 404 branches for missing entries/notes/comments |
| `time_utils.py` | 86% | 22-23 (`parse_timestamp`, unused by any current caller — dead code candidate) |

This matches `sandbox/README.md`'s documented "39 passed" for this environment
(the WeasyPrint PDF test runs here, unlike on a macOS host). No test was
skipped, none xfailed. This is the Phase F baseline that later coverage
readings in `COVERAGE.md` are measured against.

Frontend: `npm run typecheck` and `npm run lint` both pass clean (no output,
exit 0) as of this commit.

## 8. Prior review documents already accounted for

- `docs/code_review.md` — MVP review. Findings 1-9 (Critical/High/Medium) are
  fixed and verified (confirmed independently above: path traversal fixed,
  timestamps canonical, delete-permission and audit-log gaps closed, CSV
  escaping present). Finding 10 (Low, 8 items) is open by explicit prior
  choice. Relevant open items folded into Phase F gap-analysis milestones below
  rather than re-discovered: dead `session_secret`, unmaintained `passlib`,
  floating `"latest"` frontend deps, no live-update mechanism (superseded by
  ADR 0003, Phase 3), single-line note/comment composers (superseded by ADR
  0005 + Phase 3 rich text), numeric-only author filter, N+1 queries (measured
  acceptable in `OPEN-QUESTIONS.md` Q7 for the dashboard case; AI context
  building N+1 remains open), no logging, dead defensive branch in
  `export_service.fetch_export_data`, `conftest.py` mutates global settings
  without restoring them, no login rate limiting, expired sessions never
  purged.
- `docs/OPEN-QUESTIONS.md` — all Q1-Q11 resolved; Q1 (OpenAI vs OpenRouter) is
  what motivated the `docs/v2_review_brief.md` fix in this session (§4.1.6).
- `docs/adr/0001-0012` — all "Accepted (v2)"; no ADR is proposed or superseded
  by anything found in this reconnaissance pass.
