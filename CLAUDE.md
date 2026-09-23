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
npm test             # vitest run
npm run test:coverage
npm run e2e          # playwright; builds the app and starts scripts/e2e-server.sh
```

```bash
make check-fast      # the inner-loop gate
make check           # the full gate (Docker portion deferred to the host)
make seed            # demo data; prints the seeded users and what each can see
make reindex         # rebuilds the FTS5 search index from the source tables
make backup          # VACUUM INTO snapshot, retained on a rolling window (ADR 0011)
make restore BACKUP=path/to/app-<timestamp>.db   # stop the app first
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
`routes_export`, `routes_notifications`, `routes_search`. Shared logic lives in small
helper modules rather than a service layer: `permissions.py`, `time_utils.py`,
`audit_utils.py`, `timeline_utils.py`, `notification_service.py`, `ai_service.py`,
`export_service.py`, `search.py`.

### One API surface

Everything a client calls is `/api/v2/*` (`docs/ARCHITECTURE.md`, "API
versioning"). v1 carried the shapes the MVP frontend read; milestone 1.3 opened
the v2 boundary with the two breaking changes below, milestone 2.9 ported the
rest, moved the frontend and removed v1. `docs/ROADMAP.md`'s breaking-changes
table scheduled that removal for the end of Phase 2.

- **Pagination** (`pagination.py`). Every collection read takes `?limit`
  (1-200, default 50) and `?cursor` and answers `{"items", "next_cursor"}`.
  Keyset, not offset: the cursor is an opaque base64 of the last row's
  `(sort value, id)`, and each query asks for `limit + 1` rows so the last page
  reports `next_cursor: null` rather than handing back a cursor that resolves to
  nothing. Every paginated `ORDER BY` therefore ends in the row id — a sort column
  alone is not unique, and a cursor over a non-unique order skips rows.
- **Error envelope** (`errors.py`). Every failure is
  `{"error": {"code", "message", "fields"?}}`. With one surface left the path
  test (`is_api_path`) separates the API from the page routes this same process
  serves, not one version from another — which is why the two error paths that
  never reach a handler carry the envelope themselves: the CSRF rejection in
  `security.py` (middleware answers before routing) and `main.py`'s
  `/api/{path:path}` catch-all.

Two paths sit outside `/api/v2` on purpose: `/api/health`, an operations probe
read by the container's `HEALTHCHECK` and `scripts/docker-smoke.sh` rather than
by a client (**D-094**), and that catch-all.

The per-table SQL constants that existed so a v2 route could not drift from its
v1 twin (`ACCESSIBLE_OPPORTUNITIES_SQL`, `AUDIT_LOG_ROWS_SQL`,
`NOTE_VERSION_ROWS_SQL`) are gone with the second caller; each query is written
where it runs. `SHARE_ROWS_SQL` stays because it is still read twice, by the
paginated list and by `fetch_share_rows`, which the two share writes use to
return the row they touched. `tests/test_api_v2.py` holds the envelope and
cursor-walk tests, and the parametrized guard that every v1 path now 404s.

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
presented session row is deleted) and `POST /api/v2/auth/password` invalidates every
session of that user. `uploads.py` and `sanitize.py` hold the upload and HTML
rules for the Phase 4 and Phase 3 features that will use them; each explains in
its docstring why it exists before its feature does.

`database.py` opens a fresh connection per operation via the `db_connection()`
context manager, which sets `PRAGMA foreign_keys = ON`, `journal_mode = WAL`, and a
5s `busy_timeout` on every connection (`tests/test_database.py` guards all three).
There is no connection pool and no request-scoped session — routes open a
connection, do their work, `commit()`, and close.

### Search

`GET /api/v2/search` is ranked, snippeted, cross-opportunity keyword search over
entries, notes and comments, and the timeline's `?q=` filter is the same index
asked a narrower question (ADR 0007). Four things about it are load bearing:

- **The index is a contentless FTS5 table** (`search_index`, revision
  `20260917_0002_search_index`), so it stores no text. `snippet()` and
  `highlight()` are therefore unavailable and `search.build_snippet` produces
  the excerpt by re-reading the matched row; the table also cannot be scanned
  without a `MATCH`, which is why every query in `search.py` starts from one.
  Contentless is what keeps it cheap — the ADR measured +13 MB against +212 MB
  for a content-duplicating index.
- **The rowid is the document identity**: `source id * 4 + kind code`, kind
  codes 0 entry, 1 note, 2 comment. That bijection is why no mapping table
  exists. The encoding is written twice — as constants in `search.py` and as
  arithmetic in the revision's trigger SQL — and
  `tests/test_search.py::test_writes_are_indexed_under_the_documented_rowid`
  is what keeps the two in agreement.
- **Triggers maintain it, including the soft-delete transitions.** Nine of
  them, `AFTER INSERT/UPDATE/DELETE` on each of the three tables. The UPDATE
  trigger covers an edit, a soft delete and a restore with the same two
  statements: remove what was indexed (`old.*`, guarded on
  `old.deleted_at IS NULL`), index what is now visible. A contentless table
  cannot be `UPDATE`d or `DELETE`d from with ordinary SQL, so removals use
  FTS5's `'delete'` command, which needs the row's previous column values.
  Those queries still filter `deleted_at IS NULL` at every level they join
  through — a read that trusts the index to be current is a read that trusts a
  cache.
- **Permissions are inside the query**, not a filter over its results
  (`permissions.ACCESSIBLE_OPPORTUNITY_IDS_SQL`): search is the first read that
  spans opportunities, so it cannot resolve a role first the way every other
  route does. A page of 50 is 50 rows the caller may read.

`make reindex` (`backend/tools/reindex.py`) rebuilds the index from the source
tables, for the two cases ADR 0007 names — corruption, and a change that
invalidates the stored terms such as a different tokenizer or a new document
kind. Its SQL is duplicated in the revision's backfill, because a revision is
frozen in time and must not import application code;
`test_rebuild_reproduces_the_index_the_migration_built` fails if the two drift.

### Notifications

`GET /api/v2/notifications` (milestone 1.7) is the inbox: full history,
optional `?type=` filter, keyset-paginated. v1 answered a narrower question
from the same rows — unread-only, so marking a notification read made it
disappear (`WHERE read = 0`) — and that was the one place a v2 route did not
mirror its v1 twin. It went with the rest of v1 in milestone 2.9;
`read_at IS NULL` is the same set, and a reader now keeps what they have read.

- `read_at` (nullable, `NULL` = unread) is the source of truth added by
  revision `20260920_0003_notification_history`. The older boolean `read`
  column is still written but no longer read by any route (**D-095**):
  dropping it is a migration with no client-visible effect, so it is left for
  whichever phase next touches this table.
  `notification_service.mark_notification_read`
  and `mark_all_notifications_read` write both columns together — via
  `COALESCE(read_at, ...)` so a second mark-read is idempotent — so the column
  stays truthful for anyone reading the database directly.
- `grouped_key` rides along unpopulated. It exists now so Phase 5's digest
  batching (§9's "3 new comments on Acme Expansion, not three emails") is a
  query change, not another migration.
- Two write routes over the same rows:
  `PATCH /api/v2/notifications/{id}/read` for one and
  `POST /api/v2/notifications/mark-all-read` for everything. The frontend
  inbox panel (`app/NotificationMenu.tsx`) reads the history and marks
  through both.

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

### Health and backups

`GET /api/health` (`main.py`) reports substance, not just liveness (ADR 0011):
`schema_version` (the `alembic_version` row), `database_writable` (a
`BEGIN IMMEDIATE` that immediately rolls back — cheap, and the same lock a real
write would need, so a read-only mount or a full disk is caught before it
becomes a 500 somewhere else), and `last_backup_at`. Opening the connection at
all is inside the same `try`, because `get_connection()` asserts WAL mode,
which is itself a write — a genuinely unwritable database can fail there
before any query runs.

`app/backup.py` is `VACUUM INTO`, which snapshots a consistent copy without
locking out writers (unlike copying `app.db`, which can capture a torn WAL
checkpoint). `make backup` writes a timestamped snapshot to `backup_dir()`
(default: a `backups/` directory next to the database file — `/data/backups`
under the shipped `DATABASE_URL`) and prunes down to `BACKUP_RETENTION_COUNT`
(default 7). `make restore BACKUP=<path>` reverses it — stop the application
first, since it deletes the live database's `-wal`/`-shm` sidecars before
overwriting `app.db` in place. `tests/test_backup.py` exercises the full
round trip, not just that a snapshot file gets created: ADR 0011 requires the
restore to be "actually exercised," not assumed.

There is no scheduler wired to `make backup` yet — ADR 0004's APScheduler
lands in Phase 5, and standing up a second scheduling mechanism ahead of it
would be scope this milestone doesn't own. Until then, run it by hand or from
host cron.

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

### Edit history

A third mechanism, and the one an edit leaves behind (milestone 2.10,
`AGENTS.md` invariant 8). Three tables, one shape: `note_versions` from the
baseline, `opportunity_versions` and `timeline_entry_versions` from revision
`20260923_0006_version_history`. `versioning.py` is the only writer — a fourth
editable thing adds a `VersionedTable` there rather than a fourth `INSERT`.

- **A version is a snapshot, not a diff.** Every editable field, every time, so
  a partial `PATCH` still records the whole state and no reader has to
  reconstruct one from a chain with a gap in it. The route writes it *after*
  the `UPDATE`, from the row read back, and stamps it with that write's own
  time — for an opportunity that is the `updated_at` the same statement set.
  Version 1 is written at creation, so the history opens with what the thing
  said on day one. `POST /opportunities/bulk`'s stage change records one too:
  it is the same edit, asked for in bulk.
- **The read is owner-only** (**D-096**), which is the audit log's rule and a
  change from the one shipped route — `GET /api/v2/notes/{id}/versions` was
  open to every role while it was the only history and nothing called it. There
  is no admin role here, so `AGENTS.md`'s "owner or admin" resolves to the
  opportunity owner. All three are keyset-paginated oldest-first, like the
  audit log.
- **System entries have no history** and are skipped by the backfill: they
  cannot be edited (403), so the route answers an empty page rather than a copy
  of the row beside it.
- **The backfill's version 1 is a baseline, not a recorded edit** (**D-097**).
  Every pre-existing row got one from its current values; for a row edited
  before the revision the earlier values were overwritten in place and are
  gone, so it reads as the oldest state this database can still show.
- The frontend is one screen for all three (`app/HistoryDialog.tsx`):
  `lib/domain.ts` declares which fields each kind snapshots and how each reads,
  `versionChanges` compares two versions without knowing which kind it holds,
  and the read hook arrives as a prop. Version 1 renders as the whole state,
  every later one as only what it moved. The button sits beside the exports on
  the opportunity, and on each entry and note, rendered only for the owner.

### Soft deletes and undo

Nothing is hard-deleted. `soft_delete.py` is the only place user data is deleted:
it stamps `deleted_at` and cascades it down the opportunity → entry → note →
comment tree, and every read query filters `deleted_at IS NULL` at each level.
Routes call those helpers rather than writing their own `UPDATE ... SET
deleted_at`, so a new delete path cannot quietly forget a level of the tree. An
edit to any of the three editable things additionally appends a version rather
than overwriting (see "Edit history" above).

The same module holds the inverse, added by milestone 2.4b so the UI could stop
confirming and start offering Undo (`docs/UX.md`): `restore_opportunity`,
`restore_timeline_entry`, `restore_note`, `restore_comment`, behind
`POST /api/v2/<kind>/{id}/restore`. Three
things about them:

- **A restore is scoped by the delete's stamp.** One cascade writes one
  `deleted_at` value across everything it takes, so the restore asks for that
  value back and a note deleted separately stays deleted. The route reads the
  stamp off the row and passes it in, rather than each helper reading it again.
  `utc_now()` is second-resolution, so two deletes in the same subtree within
  one second share a stamp and undo takes both back — bounded and accepted
  (D-067).
- **A child cannot be restored while its parent is deleted**, and restoring
  something that is not deleted is a 404, the same answer as one that never
  existed. Permission is the delete's rule exactly: author-or-owner for
  timeline items, and owner-only for an opportunity — where every other actor
  gets 404, not 403, because deleting the opportunity deleted the share rows
  that made them visible to each other.
- **Undo writes its own audit row** (`*_restored`) rather than removing the
  delete's: the log is the sequence of what happened.

`tests/test_restore.py` holds the round trips, including the one that proves a
restored entry is searchable again — the FTS5 UPDATE trigger already covered
the restore transition, which is why no index code changed.

`tests/test_soft_delete.py` fails the build if any module in `app/` contains a
`DELETE FROM` against a table in `soft_delete.USER_DATA_TABLES`. `sessions` is
deliberately not in that list — a session is ephemeral authentication state, not
user content, and logging out really does delete the row.

### AI agent

Read-only by construction, not by prompt instruction, in two independent ways.
`routes_ai` opens `database.read_only_connection()` — `PRAGMA query_only = ON`, so
SQLite itself raises on any write from that path, and it is a pragma rather than a
`mode=ro` URI because the database runs in WAL. It then assembles the full
chronological timeline as text (`ai_service.build_timeline_context`), sends it with
the question via `client.responses.create(..., store=False)`, and returns a string.
No tool surface is exposed to the model, and none should be added. Both halves are
pinned by `test_invariant_*` tests. Viewers may ask
questions; the endpoint uses `require_opportunity_access`, not
`require_timeline_write`.

### Frontend

Next is a bundler here, not a server (ADR 0005): `output: "export"` emits one
HTML file from the optional catch-all `app/[[...slug]]/page.tsx`, whose
`generateStaticParams` deliberately returns only the root. FastAPI answers every
unmatched path with that same file (`main.py`'s `serve_frontend`), so a deep
link like `/search?q=finance` loads the shell and the client router takes over.
Adding a second Next route would emit a second HTML file and split the SPA;
routes go in `app/AppRoot.tsx` instead.

`AppRoot` is the whole client runtime: the TanStack Query provider, then
`BrowserRouter` over `AppRoutes`. It renders nothing until it is in a browser —
the export renders this tree once in Node, where `BrowserRouter` has no history
to read — which is also why the emitted `index.html` body is empty.
`AppRoutes` is exported separately so the tests mount the real route table
inside a `MemoryRouter` (`app/test-app.tsx`) rather than a copy of it.

Three routes. `/search` is `app/SearchPage.tsx`; `/` is `app/DashboardPage.tsx`,
a **layout route** with two children — the index, which is the "select an
opportunity" panel, and `opportunities/:opportunityId`
(`app/OpportunityPanel.tsx`). The board therefore stays mounted while the child
route swaps the panel beside it, which is what gives an opportunity its own URL
without reloading the list behind it (D-054). Anything else redirects to `/`.
`OpportunityPanel` re-keys its body on the id, so filters and a half-finished
entry edit cannot leak from one opportunity into the next.

Milestone 2.1 decomposed the former `app/Home.tsx` — 1,863 lines, 28 `useState`
hooks, every read copied into component state — into these components, none
over 200 lines and each holding only its own form state: `AuthPanel`, `TopBar`,
`NotificationMenu`, `OpportunityForm`, `StageBoard`, `SharingPanel`,
`TimelineFilterBar`, `TimelineEntryForm`, `TimelineEntryList`, `NoteBlock`,
`AiSidebar`.

### Four views over one list

Milestones 2.7 and 2.8 gave the dashboard four renderers over one dataset, and
the shape of that is worth knowing before adding a fifth:

- **`DashboardPage` filters and sorts once** (`applyOpportunityView`) and hands
  the result to `StageBoard`, `OpportunityList`, `OpportunityTable` or
  `OpportunityCalendar`. Which one is a field on the URL-serialized view state
  (`?opportunities.view=table`), so a view is linkable, survives a reload, and
  is what a saved view stores beside its filters. Switching costs no request
  and keeps the cursor, the bulk selection and the filters where they were.
- **The order the reader sees is one function**, `viewOrder` — stage column by
  stage column on the board, sort order in the list and the table, day by day
  in the calendar — and `j`/`k`, `x`, `e`, Enter and shift-click ranges all
  walk it. The card, the row, the table row and the calendar chip render
  through one hook, `app/useOpportunityItem.ts`, which holds the focus effect
  (D-072's `focusin` subtlety lives there), Enter to open, the checkbox
  (D-081), and the shared `opportunity-item` class that the focus ring, the
  checked state and `Esc` are all written against.
- **The cursor walks what is drawn; the selection is everything filtered in.**
  Those are the same set in three views and differ in the calendar, which
  draws one month — so `ordered` (the cursor, ranges) comes from `viewOrder`
  and `checkedOpportunities` comes from the filtered list. Deriving both from
  `viewOrder` silently shrank a live selection on switching to the calendar.
- **The table's own two settings** are the visible columns
  (`app/ColumnPicker.tsx`, `?opportunities.columns=`) and the sort, which its
  column headers write into the same `sortField`/`sortDirection` the filter
  bar's dropdowns do — one setting asked two ways. It is not a `<table>`:
  windowed rows cannot carry honest table semantics, so each cell names its
  column in visually-hidden text and the sort state rides on the row region's
  label (**D-090**). Inline cell editing is 2.11's, not here (**D-087**).
- **The calendar places `expected_close_date` only.** A follow-up date lives
  on a timeline entry and there is no cross-opportunity read for those; Phase
  4 builds one (**D-088**). Deals with no close date are listed under the grid
  rather than dropped. The month is `?opportunities.month=YYYY-MM`, and empty
  means the reader's own month resolved at render, so a shared link opens
  where the reader is. Every date is handled as `YYYY-MM-DD` text in UTC and
  never parsed into a local `Date` — `new Date("2026-12-01")` is the previous
  day west of Greenwich.
- **Every stage change is the same write.** A card dropped in another column,
  the move-to-stage select on a card or row (`app/MoveToStage.tsx`), and the
  `[`/`]` chords all call `DashboardPage`'s `moveToStage`, which is
  `useChangeOpportunityStage`: a partial `PATCH {stage}`, optimistic, rolled
  back with a toast, invalidating the timeline because the server writes the
  `stage_change` system entry. The drag itself is the browser's own HTML5
  drag-and-drop with no library (D-080); the dragged card is held in React
  state rather than read back from `dataTransfer`, because a `dragover` handler
  may not look inside the payload. Only an owner's card is draggable and only
  an owner's card carries the select — changing an opportunity's fields is
  owner-only, and the select is what makes the board operable without a mouse
  (`docs/DESIGN-SYSTEM.md` calls that the requirement most likely to be
  skipped).
- **Density is a root attribute**, not a component variant (D-075, **D-089**):
  `lib/density.ts` stores Comfortable or Compact and writes `data-density` on
  `<html>`, `app/globals.css` carries `--row-height`, `--row-text`,
  `--row-line` and the two cell paddings under `:root` and
  `[data-density="compact"]`, and anything that varies reads those. Same shape
  as `lib/theme.ts` with two answers rather than three — nothing outside the
  app has an opinion about row height. The control (`app/Density.tsx`) sits
  beside the view switcher and only while the table is on screen; the theme
  control stays in the top bar because it applies everywhere.
- **The create/edit form is a dialog**, not a column (D-079): opened from the
  page header, by `c`, and by Edit on any card or row, on the same
  `app/Modal.tsx` shell as the palette. `TopBar` therefore carries no page
  title — the screen names itself in its own header, beside the view switcher
  and the create button.
- **Empty is two different answers.** `DashboardPage` renders the skeleton,
  the "there are none yet" onboarding panel and the "your filters removed them
  all" panel itself, so neither view component is ever asked to draw nothing.

**Writes are optimistic where the cache already holds what changes** (2.4b):
the four deletes and the note edit apply in `onMutate`, snapshot what they
overwrote, and put it back in `onError` — `docs/UX.md`'s "applies immediately,
reconciles on response, rolls back with an explanatory toast". Creates are not,
deliberately: the server assigns the id, so there is nothing truthful to render
until it answers (D-068). A delete or a restore also invalidates
`keys.allAuditLogs`, since both write an audit row and neither knows which
opportunity the row belongs to.

**Server state does not live in components.** `lib/queries.ts` declares every
read and write the app makes against the query cache: the query keys, the six
reads, and each mutation with what it invalidates. A view calls a hook; a write
invalidates a key. Do not add a bare `apiRequest` call to a component — that is
the pattern ADR 0005 calls blocker B1, and 2.1 is what removed the last of it.
Four of the reads go through `fetchAll`, which walks `next_cursor` to the last
page: the API paginates every collection, and the board's cursor, its bulk
selection and the calendar's month are all derived from the whole filtered
list rather than from a window of it (**D-093**). The other two ask for one
page with an explicit limit, because an inbox and a saved-view menu are read
from the top.
Two things in there are worth knowing before changing them: the AI transcript is
cache state under `["ai-conversation", id]` because it has to outlive the route
(D-055), and the cache is dropped on *sign-in*, not sign-out, because observers
are still mounted for one render after logout and removing their queries makes
them refetch (D-056).

The units worth testing directly, each in its own module:

- `lib/api.ts` — `apiRequest<T>()`, the only fetch wrapper
  (`credentials: "include"`, echoes the CSRF cookie on unsafe methods, throws on
  non-2xx using the envelope's `error.message` — the one shape the API answers
  with since v1 went).
- `lib/query.ts` — `createQueryClient()`, the single TanStack Query
  configuration (no retries: `apiRequest` throws on 401 and 422 too).
- `lib/snippet.ts` — turns a search snippet's match offsets into runs to
  highlight. The API sends text and offsets, never markup.
- `lib/time.ts` — the UTC/`datetime-local` conversions at both boundaries.
- `lib/permissions.ts` — `canManageOpportunity` / `canWriteTimeline` /
  `canChangeItem`, the client mirror of `backend/app/permissions.py`. They decide
  which buttons are offered, never who is allowed to do what.
- `lib/notifications.ts` — the sentence shown for each notification type.
- `lib/domain.ts` — the fixed stage list, the entry types, the short names for
  the generated schemas, and the two view states (`TimelineFilters`,
  `OpportunityViewState`) with `applyOpportunityView`, which filters and sorts
  the already-fetched opportunity list in the client. One definition, because
  several views read them. Also what the four opportunity views share:
  `viewOrder` (reading order), `adjacentStage` (`[` and `]`, which stop at the
  ends of the fixed list), `formatMoney`, the `sortFields` and
  `opportunityColumns` lists with `columnsFromState`/`opportunityCell`, and the
  calendar's date arithmetic (`resolveMonth`, `shiftMonth`, `calendarWeeks`,
  `monthOrder`).
- `lib/density.ts` — Comfortable and Compact as a preference resolved to one
  root attribute. Carries no sizes, the same way `lib/theme.ts` carries no
  colours.
- `lib/viewState.ts` — the URL/object round trip both view states use.
- `lib/keyboard.ts` — the keyboard map, and the listener that serves it. See
  "Keyboard map" below.
- `lib/palette.ts` — the command palette's fuzzy subsequence matcher.
- `lib/theme.ts` — light and dark as a preference resolved to one of two
  palettes. It carries no colours: it decides which palette is in force and
  writes `data-theme` plus `color-scheme` on `<html>`, while `app/globals.css`
  holds both sets of role values (see "Design tokens and themes").
- `lib/contrast.ts` — WCAG relative luminance and contrast ratio, used by
  `lib/contrast.test.ts` to re-run `docs/DESIGN-SYSTEM.md`'s audit against the
  tokens themselves.
- `app/Toasts.tsx` — the toast surface and `useUndoableDelete`, the one
  definition of "delete it, and say so with a way back" (milestone 2.4b). The
  region is a `role="status"` live region, never focused, so a reader keeps
  their place; the toast lasts `TOAST_DURATION_MS` (10 s, the window
  `docs/UX.md` names). Both legs go through `mutateAsync`, because the control
  that started the delete has usually unmounted by the time it resolves —
  deleting a note unmounts the note — and TanStack Query drops
  `mutate(vars, { onSuccess })` once the observer has no listeners.
- `app/MarkdownText.tsx` — note and comment bodies, rendered through
  `rehype-sanitize` with an explicit `http`/`https`/`mailto` protocol allowlist.
  Keep that allowlist if you touch the Markdown pipeline.
- `app/VirtualList.tsx` — a generic `<T>` wrapper over
  `@tanstack/react-virtual` (milestone 2.3, roadmap: "400 opportunities will
  not render unvirtualized"). `StageBoard` renders each stage column through
  it, and `OpportunityList` its rows, instead of mapping every filtered
  opportunity into the DOM; row height
  is measured after mount, so `estimateItemSize` only has to seed the first
  layout. `activeIndex` scrolls a column to the keyboard cursor, and
  `DashboardPage` passes it **only while the cursor was moved by the
  keyboard** (`followCursor`, D-072): a card focused by a click is already
  where the reader is looking, and scrolling then moves the control out from
  under the click that focused it, between the mousedown and the mouseup. jsdom never lays anything out, so `vitest.setup.ts` stubs
  `offsetHeight`/`offsetWidth` globally — without it the virtualizer
  (correctly) treats every test's viewport as zero pixels tall and renders
  nothing. This only windows what gets rendered, not what gets fetched:
  `useOpportunities` walks `GET /api/v2/opportunities` to its last page
  (D-063 deferred that switch to 2.9, **D-093** is how 2.9 made it).
- `app/Modal.tsx` — the dialog shell the command palette and the shortcut
  reference share — and, since 2.7, the opportunity create/edit form — on
  Radix's `Dialog` since 2.5. Radix owns the portal, the
  focus trap, the ARIA wiring and hiding the rest of the page from assistive
  technology; two rules stay this app's own. `Esc` is answered on the dialog and
  stops before the document-level keyboard map sees it — the board is mounted
  behind the palette and binds `Esc` itself. And returning focus is part of
  **dismissing** (Esc, the backdrop, the Close button), not of unmounting: a
  dialog that closes because it moved the page lets focus fall to the document,
  so the next Tab starts at the top of the screen the reader is now on (D-066).
  That restore runs in the unmount cleanup rather than in the dismiss handler,
  because Radix's focus guards are still on the page while `onClose` runs and
  whichever focuses first loses.
- `app/ConfirmDialog.tsx` — the one place this app asks "are you sure",
  replacing the `window.confirm` placeholder `lib/confirm.ts` held.
  `useConfirm()` returns a promise, so the three call sites read the way the
  `window.confirm` they replace did; Radix's `AlertDialog` is underneath. The
  two deletes that cascade — one opportunity, and a bulk selection — carry the
  **typed** confirmation `docs/UX.md` asks for (the name typed back for one, the
  word `delete` for several, since no single name describes what goes). Removing
  someone's access asks plainly: there is no restore route, but the grant can be
  made again (D-069). Everything else offers Undo instead (`app/Toasts.tsx`).

### Keyboard map

`docs/UX.md` treats keyboard operation as a feature, not polish, and milestone
2.4a is where it landed. Three things are load bearing:

- **One declaration.** `lib/keyboard.ts`'s `shortcutGroups` is the array the
  `?` reference screen renders *and* the source of the `Chord` union type the
  views bind against (`Partial<Record<Chord, () => void>>`). A key documented
  but never bound, or bound but never documented, is a type error. Keys whose
  feature does not exist yet are deliberately absent rather than inert: `x`
  arrives with bulk selection, `g t` with Phase 4's tasks (D-065).
- **Each view binds only what it can act on.** `ShortcutsProvider` owns the
  chords that mean the same thing everywhere (`Ctrl K`, `?`, the `g`
  sequences); `DashboardPage` owns the cursor over whichever view is on screen
  (`j`, `k`, `e`, `x`, `/`, `[`, `]`, `Esc`); `OpportunityPanel` takes `c` off the dashboard while a timeline is
  open, so "create" means an entry there and an opportunity on the board. Two
  views never answer the same chord, and a binding cannot outlive the thing it
  acts on.
- **Single keys stop at a text field.** `chordFor` returns nothing for a
  letter typed into an input, textarea, select or contenteditable —
  `isTypingTarget` — while `Ctrl K` and `Esc` still work there, which is what
  `docs/UX.md` means by "from anywhere including inside inputs". The guard test
  is `does not treat what the reader types as commands` in
  `app/Keyboard.test.tsx`; without that check, typing a note fires half the
  map.

The keyboard cursor (`focusedId` in `DashboardPage`) is separate from the
opened opportunity (`selectedId`): `j` and `k` walk the items without opening
anything, in `viewOrder` — stage column by stage column on the board, sort
order in the list, which is the order they are read in. Because both views are
virtualized, the row the cursor moves to may not be in the DOM, so
`VirtualList` takes an `activeIndex` and scrolls to it. `[` and `]` move the
focused opportunity one stage either way, which is the drag done from the
keyboard, and do nothing on an opportunity the reader does not own.

### View state and saved views

The applied filter/sort set is in the URL, not in component state — that is
what makes a view linkable, reloadable and shareable (milestone 2.2). Two of
them are live at once, because the board stays mounted beside the open
timeline: `OpportunityViewState` over the opportunity list and
`TimelineFilters` over one opportunity's entries. They share the field name
`q`, so `lib/viewState.ts` namespaces each state's parameters by the entity it
belongs to — `opportunities.stage`, `timeline.order` — and `paramsWithState`
merges into the existing query string rather than replacing it. Both halves
are load bearing: without the prefix the board's keyword filters the timeline,
and without the merge writing one state drops the other's parameters (D-059).
The prefix is the same `entity` a saved view is filed under, so there is no
second naming to keep in sync.

A **saved view** (`saved_views`, `routes_saved_views.py`,
`app/SavedViewsMenu.tsx`) is a named copy of one of those states, personal or
shared, with at most one default per user per entity. Three things about it:

- It is **not opportunity-scoped**, so `permissions.py` does not apply. The
  rule is creator-only write and creator-or-shared read, and a view that is
  neither answers 404 like everything else (existence does not leak). `shared`
  means visible to every signed-in user — this app has no teams (D-060).
- `filters` and `sort` are **opaque JSON**: whatever the URL held, stored as
  key/value strings with a size cap and no schema. A new filter field is a
  frontend change, not a migration.
- The **partial unique index** `idx_saved_views_default_per_user` enforces the
  one-default rule in the schema, not in application code; the routes clear
  the previous default in the same transaction before setting a new one.

What a shared view shares is its **filters, not its rows** — every list it
feeds is permission-filtered per reader, so two people applying one view see
different opportunities, and that is correct. Milestone 2.13 is the wording
that stops it being a surprise (**D-076**, **D-082**), and it is all in the
frontend — the storage and the routes were already right:

- `lib/domain.ts` holds the vocabulary in one place —
  `savedViewVisibility` reads the single `is_shared` flag as the three facts
  it carries (mine and private, mine and everyone's, someone else's),
  `savedViewLabel` is the dropdown line, and `matchesSavedView` is how the
  strip knows which view is applied. Nothing records that: applying a view
  only writes its filters into the URL, which is the whole mechanism behind a
  shareable view, so the applied view is recognised by comparing — and the
  line therefore disappears by itself when a filter changes.
- The visibility choice is **explicit at save time** (`SavedViewFields.tsx`),
  in a dialog, with the sentence that sharing publishes the view's *name* to
  every signed-in user while its results stay permission-filtered.
- **Editing and deleting live in `ManageSavedViews.tsx`**, not beside every
  name — `AGENTS.md`'s Design bar. The delete confirms **in the row** rather
  than through `app/ConfirmDialog.tsx`: that is a second modal layer, and two
  Radix focus traps over one page fight for focus instead of stacking (it
  recursed until the test worker aborted).
- Both of the dashboard's empty answers say the set being filtered is what
  *this* reader may see, which is the sentence that would have prevented the
  original confusion.

Each filter and sort control carries a **visible caption as well as its
`aria-label`** (`OpportunityFilterBar`, `TimelineFilterBar`). The caption is
the short word and the `aria-label` stays the longer sentence that tells the
board's bar from the timeline's, so both stay addressable while the screen
says what each control is. One consequence for tests: a control is now
reachable by either string, so a query for a caption the app uses twice
(`Stage`, in the filter bar and in the opportunity dialog) has to be scoped to
one of them.

The board's filtering and sorting happen **in the client**, over the list
`useOpportunities` holds whole — D-061 chose that, and **D-093** kept it when
2.9 moved the read onto paginated `GET /api/v2/opportunities`, because the
cursor, the bulk selection and the calendar's month are derived from the same
result and none of them is a window.

`lib/api-types.ts` is generated from the OpenAPI schema; never hand-edit it.

### Design tokens and themes

`app/globals.css` opens with the token set from `docs/DESIGN-SYSTEM.md`
(milestone 2.5), and nothing below it names a colour directly. Four things are
load bearing:

- **Roles, not brands.** The brand ramp (`--teal-500/600/300` and siblings) is
  read only by the semantic roles beneath it — surfaces, text, borders, the focus
  ring, fills that carry text, badge colours. A rule asks for `--text-link`,
  never for teal. That is what makes the dark palette a swap of one block
  instead of an audit of every rule.
- **A token is either a text token or a fill token, never both.** The brand
  colours are sound as fills and unsafe as text: teal `#0f9d8c` on white is
  3.38:1. The `-600` variants are the darkened counterparts — text, and fills
  that carry white text — and they are the corrected contrast values the roadmap
  names.
- **Both palettes are measured, in the unit suite.** `lib/contrast.test.ts`
  reads this stylesheet, resolves `var()` indirection, and asserts every pair the
  app paints at AA in light *and* dark. A token edited to an unreadable value
  fails there, naming the token, before axe renders a page. `DEFERRED_AXE_RULES`
  in `e2e/helpers.ts` is now empty, and `e2e/07-accessibility.spec.ts` audits
  every screen once per `prefers-color-scheme`.
- **The theme is one attribute, resolved in JavaScript** (D-074), not a
  `prefers-color-scheme` block: a media query cannot be added to a selector list,
  so supporting an explicit choice that way would mean two copies of the dark
  palette. `lib/theme.ts` resolves the stored preference against the media query,
  `app/Theme.tsx` provides it and renders the System / Light / Dark control in
  the header, and the export's empty shell means there is no server-rendered
  content to flash the wrong colour (ADR 0005).

## Testing

`make check-fast` is the inner loop and `make check` is the full gate; the Docker
build and smoke test are the one piece that cannot run in the autopilot sandbox
and are deferred to `scripts/autopilot-gate.sh` on a host.

**Backend** (`backend/tests/`) mirrors the routers. `conftest.py` points
`settings.database_url` at a per-test `tmp_path` database and yields a `TestClient`;
tests drive the app through real HTTP calls and switch users with `signup` /
`login` / `logout` on one client. Two autouse fixtures apply to every test: the
rate limiter is reset (it is process-global by design), and `no_live_network`
fails any test that opens a socket off this machine — so a forgotten OpenAI mock
is an immediate, attributable failure rather than a real API call.

Three suites carry rules rather than features and should not be treated as
ordinary tests:

- `test_authorization_matrix.py` — every endpoint × {owner, editor, viewer,
  unrelated, anonymous}. The endpoint list is read out of the running app
  (`route_registry.py`), so **a new route with no entry in `MATRIX` fails the
  build**. Add the expectation with the route.
- `test_invariants.py` — the rules from `AGENTS.md` that the product may not
  break, named `test_invariant_*`. Joined by
  `test_soft_delete.py::test_invariant_no_hard_deletes_of_user_data` and
  `test_ai.py::test_invariant_ai_agent_has_no_write_tools`, which live next to
  the code they guard.
- `test_seed.py` — keeps `make seed`'s printed tour true.

**Frontend** (`frontend/`): Vitest + React Testing Library over `app/` and
`lib/` (`npm test`), with thresholds in `vitest.config.ts` set above the
project floor and never lowered. `app/test-api.ts` is a stateful fake of the
API — the page reloads a list after every write, so canned responses would test
the click and not the consequence.

**E2E** (`frontend/e2e/`): Playwright against the production build served by
FastAPI, started by `scripts/e2e-server.sh`, which rebuilds and reseeds a
throwaway database each run and deliberately starts the server with no
`OPENAI_API_KEY` so the suite cannot reach a paid API. `@axe-core/playwright`
runs on the major screens. `DEFERRED_AXE_RULES` in `e2e/helpers.ts` is a
ratchet, not an allowlist: it holds `color-contrast` only, any other rule fails
immediately, and a test asserts the deferred rule still fails — so the gate
tightens itself when the palette work lands.

Three rules the suite has already been bitten by:
- Assertions must not depend on the wall clock. The auto-generated "Opportunity
  created" entry is stamped with the current time, so anchor date windows to `now`
  (see the `days_ago` helper in `test_timeline.py`) rather than hardcoding dates.
- A guard test should be confirmed to fail against the unfixed code before it is
  trusted.
- In Playwright, do not filter a locator by text you are about to change — the
  locator stops matching mid-test. Address the element by position instead.

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
