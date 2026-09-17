# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

OppTrail — a timeline note-taking app for tracking sales opportunities. `AGENTS.md`
is the authoritative requirements document (19 numbered business requirements,
explicit MVP non-goals, permissions model, coding standards); `docs/PLAN.md` holds
the data model, API surface, and phase plan. Read both before changing behavior —
several design decisions there (soft deletes everywhere, fixed stage list,
`event_timestamp` editable but `created_at` immutable) are deliberate and tested.

`docs/v2_review_brief.md` is a prompt for a future planning session, not a
description of the current system. Its stack list is inaccurate for this codebase
(the AI agent uses the OpenAI SDK, not OpenRouter). Do not treat it as spec.

## Commands

All backend commands run from `backend/`. `Settings` loads `env_file="../.env"`, so
running from the repo root silently misses it. The checked-in `.env` sets only the
OpenAI keys, so `DATABASE_URL` falls back to the relative default and a local
uvicorn run writes `backend/app.db` — separate from the container's `/data/app.db`,
and gitignored.

```bash
cd backend
uv run pytest                                    # full suite
uv run pytest tests/test_timeline.py             # one file
uv run pytest "tests/test_timeline.py::test_deletions_are_recorded_in_the_audit_log"
uv run pytest -q --cov=app --cov-report=term-missing
uv run uvicorn app.main:app --reload             # API only, no frontend
```

```bash
cd frontend
npm run typecheck    # tsc --noEmit
npm run lint         # eslint
npm run build        # static export to frontend/out
```

Full app (builds the frontend, packages both into one container):

```bash
./scripts/start_mac.sh     # or start_linux.sh / start_windows.ps1
./scripts/stop_mac.sh
```

The start scripts run `docker run` in the foreground on port 8000 (override with
`PORT`) and bind-mount `./data` to `/data` for the SQLite file.

### Dev loop gotcha

`next.config.ts` sets `output: "export"`, and the frontend calls the API with
relative paths (`/api/...`). There is no dev proxy, and rewrites are unavailable in
export mode, so `npm run dev` alone cannot reach the backend. To exercise the real
app either build the container, or run `npm run build` and then start uvicorn from
`backend/` — the default `FRONTEND_STATIC_DIR` (`../frontend/out`) already resolves
to that build, so FastAPI serves the app and the API from one origin.

### WeasyPrint

PDF rendering needs native libraries that are not present on macOS hosts. Importing
`weasyprint` there raises `OSError` from cffi, not `ImportError` — so
`pytest.importorskip` does not catch it (see the guard in
`tests/test_export.py::test_pdf_export_produces_a_real_pdf`). The full suite runs
one test fewer on a laptop than in the container — that single skip is this one.
Verify PDF changes in Docker.

## Architecture

Single FastAPI process serves both `/api/*` and the statically exported Next.js
site. One SQLite file, created and migrated on startup. No background workers, no
websockets, no ORM — raw `sqlite3` with `Row` factory throughout.

### Backend layout (`backend/app`)

Routers are split by domain and all mounted in `main.py`: `routes_auth`,
`routes_opportunities`, `routes_sharing` (also owns the audit log endpoint),
`routes_timeline` (entries, notes, comments, note versions), `routes_ai`,
`routes_export`, `routes_notifications`. Shared logic lives in small helper modules
rather than a service layer: `permissions.py`, `time_utils.py`, `audit_utils.py`,
`timeline_utils.py`, `notification_service.py`, `ai_service.py`, `export_service.py`.

### Request security

Three cross-cutting controls, all in `security.py` and registered in `main.py` in
an order that is load bearing (Starlette runs the last-added middleware outermost:
logging → security headers → CSRF → app, so the headers are attached to CSRF
rejections too):

- **CSRF** — double-submit cookie. Every unsafe method needs `X-CSRF-Token` to
  match the non-`HttpOnly` `opptrail_csrf` cookie, login and signup included; safe
  requests issue the cookie, so the SPA bootstraps it from the page load. The
  backend test suite runs through `conftest.CsrfClient`, which echoes the header
  like the browser does — `tests/test_security.py` uses a plain `TestClient` to
  prove the middleware still rejects.
- **Security headers** — CSP (including `frame-ancestors 'none'`),
  `X-Content-Type-Options`, `Referrer-Policy` on every response. The CSP allows
  inline script because `output: "export"` emits Next's hydration payload inline
  and there is no render pass to attach a nonce to.
- **Cookie flags** — `HttpOnly` session cookie, `Secure` when
  `ENVIRONMENT=production` (a `Secure` cookie is dropped over the plain HTTP that
  development and the tests use).

`rate_limit.py` caps login and signup per source address in-process — correct
because the app is a single process in a single container, and the one place to
change if that stops being true. `auth.py` rotates the session on login (the
presented session row is deleted) and `POST /api/auth/password` invalidates every
session of that user. `uploads.py` and `sanitize.py` hold the upload and HTML
rules for the Phase 4 and Phase 3 features that will use them; each explains in
its docstring why it exists before its feature does.

`database.py` opens a fresh connection per operation via the `db_connection()`
context manager, which sets `PRAGMA foreign_keys = ON`, `journal_mode = WAL`, and a
5s `busy_timeout` on every connection (`tests/test_database.py` guards all three).
There is no connection pool and no request-scoped session — routes open a
connection, do their work, `commit()`, and close.

### Migrations

Alembic owns the schema (ADR 0002). `initialize_database()` runs on every startup
and calls `alembic upgrade head`, so a new install still needs no setup step: the
baseline revision (`alembic/versions/20260916_0001_baseline.py`) creates the whole
schema. `make migrate` applies revisions by hand. There is no `schema.sql`.

A database written before Alembic existed has tables but no `alembic_version`.
`bridge_pre_alembic_database()` repairs it once — the two guarded `ALTER TABLE`s
that used to live in `run_migrations()`, plus `normalize_legacy_timestamps()` and
`backfill_opportunity_created_entries()` — and it is then stamped at the baseline
rather than re-running it. That repair is a one-shot, not a per-boot scan, which is
why application code now supplies every timestamp explicitly instead of relying on
a column default: a bridged legacy database keeps its old `CURRENT_TIMESTAMP`
defaults (`ALTER TABLE` cannot rewrite one) and nothing normalizes a row after the
bridge has run. See `tests/test_migrations.py`.

New revisions go in `alembic/versions/` as explicit SQL — no ORM, `target_metadata`
stays `None`. A revision that changes the schema must also update
`tests/data/expected_schema.sql`, which the upgrade-from-empty test compares
against.

### Timestamps

Every timestamp the app writes uses one canonical format, `%Y-%m-%dT%H:%M:%SZ` —
fixed-width UTC, defined in `time_utils.py`. This matters because timestamps are
`TEXT` and all comparison, ordering, and range filtering is lexicographic; a mixed
format silently reorders the timeline and drops rows from date filters.

Consequences to preserve:
- Never introduce `CURRENT_TIMESTAMP`. Schema defaults use
  `(strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))`; application code uses `utc_now()`.
- Client-supplied timestamps are validated and normalized in `schemas.py`
  (`canonical_timestamp`, `canonical_date`). Validating at the boundary is load
  bearing: an unparseable value stored in `event_timestamp` used to surface as a 500
  on the dashboard for every user sharing the opportunity.
- The frontend converts at both boundaries — `localInputToUtc` on write,
  `parseTimestamp` / `formatTimestamp` on read. `datetime-local` inputs are always
  local wall-clock time.
- `normalize_legacy_timestamps()` in `database.py` rewrites older rows on startup.

### Permissions

Three roles: owner (implicit via `opportunities.owner_id`), editor, viewer. Every
route resolves the role from the database through `permissions.py` — never from the
client. Absence of access returns 404, not 403, so opportunity existence does not
leak.

- `require_opportunity_access` — any role, used for reads and the AI agent
- `require_timeline_write` — blocks viewers
- `require_author_or_owner` — author of the item or the opportunity owner;
  `require_edit_permission` and `require_delete_permission` are both thin wrappers
  over it
- `require_opportunity_owner` — sharing and audit log

Editors add entries, notes, and comments freely, but changing an existing one —
editing it or deleting it — is reserved to its author and the opportunity owner.
The two rules are deliberately identical and resolve through one function, so they
cannot drift apart again (they had: see `docs/autopilot/DECISIONS.md` D-005, which
the human overruled in favour of the stricter reading). Comments stay immutable to
everyone; there is no comment edit route. The frontend `canEdit(authorId)` /
`canDelete(authorId)` helpers mirror this so buttons never offer an action the API
will reject.

### Auditability

Two separate mechanisms, both required by `AGENTS.md`:

- **System timeline entries** (`timeline_utils.create_system_timeline_entry`) are
  user-visible history — opportunity created, stage changed, sharing changed. They
  carry `system_generated = 1` and cannot be edited or deleted through the API.
- **Audit log rows** (`audit_utils.create_audit_log_entry`) are owner-only forensics
  — every share change and every deletion (`opportunity_deleted`,
  `timeline_entry_deleted`, `note_deleted`, `comment_deleted`).

Any new non-user-initiated write must be traceable to the action that caused it, and
any new delete path needs an audit row.

### Soft deletes

Nothing is hard-deleted. `soft_delete.py` is the only place user data is deleted:
it stamps `deleted_at` and cascades it down the opportunity → entry → note →
comment tree, and every read query filters `deleted_at IS NULL` at each level.
Routes call those helpers rather than writing their own `UPDATE ... SET
deleted_at`, so a new delete path cannot quietly forget a level of the tree. Note
edits additionally append to `note_versions` rather than overwriting.

`tests/test_soft_delete.py` fails the build if any module in `app/` contains a
`DELETE FROM` against a table in `soft_delete.USER_DATA_TABLES`. `sessions` is
deliberately not in that list — a session is ephemeral authentication state, not
user content, and logging out really does delete the row.

### AI agent

Read-only by construction, not by prompt instruction. `routes_ai` assembles the full
chronological timeline as text (`ai_service.build_timeline_context`), sends it with
the question via `client.responses.create(..., store=False)`, and returns a string.
No tool surface is exposed to the model, and none should be added. Viewers may ask
questions; the endpoint uses `require_opportunity_access`, not
`require_timeline_write`.

### Frontend

`frontend/app/page.tsx` is the entire application — one large client component
holding all state in `useState`, with `apiRequest<T>()` as the only fetch wrapper
(`credentials: "include"`, throws on non-2xx using the API's `detail` field). There
is no router, no state library, and no data-fetching cache; views switch on
`selectedOpportunityId`. Note and comment bodies render through `MarkdownText`, which
runs `rehype-sanitize` with an explicit `http`/`https`/`mailto` protocol allowlist —
keep that allowlist if you touch the Markdown pipeline.

## Testing

`backend/tests/` mirrors the routers. `conftest.py` points `settings.database_url` at
a per-test `tmp_path` database and yields a `TestClient`; tests drive the app through
real HTTP calls and switch users with `signup` / `login` / `logout` on one client.
There are no frontend tests.

Two rules the suite has already been bitten by:
- Assertions must not depend on the wall clock. The auto-generated "Opportunity
  created" entry is stamped with the current time, so anchor date windows to `now`
  (see the `days_ago` helper in `test_timeline.py`) rather than hardcoding dates.
- A guard test should be confirmed to fail against the unfixed code before it is
  trusted.

`docs/TEST_CRITERIA.md` defines the phase gates and the Review / Accept / Reject
decision block. `docs/code_review.md` records the findings from the last full review
and their resolution status.

## Working style for this repo

From `AGENTS.md` — these govern how changes are made here, not just what gets built:

- Simplicity over defensiveness. No features beyond what is specified, no speculative
  abstraction, no unnecessary defensive branches.
- Root-cause first. When something breaks, prove the cause with evidence before
  changing code; do not guess.
- No emojis, anywhere.
- After every file change, give a concise diff summary in chat, include user test
  steps with each phase summary, and ask for an explicit **Review / Accept / Reject**
  decision.
- **Do not commit or push until the user accepts.**
