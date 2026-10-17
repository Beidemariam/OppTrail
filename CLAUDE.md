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
make seed-scale      # the same, plus AGENTS.md's confirmed scale on top (~800k rows, 11s)
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

Milestone 4.4 added a second thing this skip hides: the attachment manifest's
table is rendered HTML here and a laid-out table there, so whether it
paginates cleanly across a page break is a question only the container
answers (`break-inside: avoid` is set on the section).

`export_service.render_export_html` renders every entry, note and comment
body as Markdown (milestone 3.5, `markdown-it-py`) rather than escaping it as
plain text — the other half of requirement 17, after milestone 3.1 gave the
composer the same node set. `commonmark`'s own default is `html: True` (raw
HTML passed through), so `html: False` is set explicitly, and the rendered
HTML is still sanitized through `app/sanitize.py`'s allowlist before
WeasyPrint sees it — two independent layers, since a body reaching this path
may have been posted straight to the API rather than through the composer
that already refuses a `javascript:` link.

## Architecture

Single FastAPI process serves both `/api/*` and the statically exported Next.js
site. One SQLite file, created and migrated on startup. No background workers, no
websockets, no ORM — raw `sqlite3` with `Row` factory throughout.

### Backend layout (`backend/app`)

Routers are split by domain and all mounted in `main.py`: `routes_auth`,
`routes_opportunities` (also owns the merged activity log),
`routes_sharing` (also owns the audit log endpoint and the member list the
mention autocomplete reads),
`routes_timeline` (entries, notes, comment threads, note versions),
`routes_tasks`, `routes_attachments`, `routes_ai`,
`routes_export`, `routes_notifications`, `routes_search`, `routes_automations`,
`routes_events` (the
one route that answers `text/event-stream` rather than JSON). Shared logic lives in small
helper modules rather than a service layer: `permissions.py`, `time_utils.py`,
`audit_utils.py`, `timeline_utils.py`, `notification_service.py`, `ai_service.py`,
`export_service.py`, `search.py`, `versioning.py`, `activity.py`, `events.py`,
`attachment_utils.py`, `automations.py`, `jobs.py`, `scheduler.py`,
`ai_filters.py`.

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
session of that user. `uploads.py` held the upload rules for the Phase 4 feature that would use
them; milestone 4.3 is that feature, and wiring it up is also what found the
module's one wrong guess — the random stored name, replaced by ADR 0008's
content addressing (**D-147**). Its tests were what made that rewrite safe,
which is the honest version of brief §4.7's bet. `sanitize.py`'s own such docstring is now out of date in the
same way: milestone 3.5 is its first caller ("WeasyPrint" below), rendering a
body's Markdown to HTML for the PDF export before WeasyPrint ever sees it —
the same allowlist `rehype-sanitize` uses in the browser, applied to the one
render path that isn't the browser.

`database.py` opens a fresh connection per operation via the `db_connection()`
context manager, which sets `PRAGMA foreign_keys = ON`, `journal_mode = WAL`, and a
5s `busy_timeout` on every connection (`tests/test_database.py` guards all three).
There is no connection pool and no request-scoped session — routes open a
connection, do their work, `commit()`, and close.

### Search

`GET /api/v2/search` is ranked, snippeted, cross-opportunity keyword search over
entries, notes, comments and attachment filenames, and the timeline's `?q=` filter is the same index
asked a narrower question (ADR 0007). Four things about it are load bearing:

- **The index is a contentless FTS5 table** (`search_index`, revision
  `20260917_0002_search_index`), so it stores no text. `snippet()` and
  `highlight()` are therefore unavailable and `search.build_snippet` produces
  the excerpt by re-reading the matched row; the table also cannot be scanned
  without a `MATCH`, which is why every query in `search.py` starts from one.
  Contentless is what keeps it cheap — the ADR measured +13 MB against +212 MB
  for a content-duplicating index.
- **The rowid is the document identity**: `source id * 8 + kind code`, kind
  codes 0 entry, 1 note, 2 comment, 3 attachment (by **filename** — the only
  text a file has here, since nothing reads inside one). That bijection is why
  no mapping table exists. The base was 4 until milestone 4.8 widened it
  (**D-167**), which is the action the 1.4 review's note asked the first
  milestone needing a fourth kind to take; four codes are free, and
  `DOCUMENT_BASE` governs the queries now rather than being a constant beside
  four literal `/ 4`s. The encoding is written twice — as constants in `search.py` and as
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

**A result lands on the match** (milestone 6.0, **D-170**). `?entry=` was
the only level a URL could name (D-124); a note or comment hit opened the
deal and left the reader to find it. `lib/domain.ts`'s `LinkTarget` is a
level and an id, `linkTargetFromParams` reads it from the URL innermost
first, `searchResultHref` is where a search result resolves to one, and
`isLinked` answers it at each level — so a new level is a case in one
function rather than another prop threaded through three components. Four
searchable kinds resolve to three levels: an attachment is rendered on the
entry it hangs off (4.3), so it is addressed by that entry.
`app/useLinkTarget.ts` holds the scroll the entry card had carried inline
since 3.2, now shared by all three. Two consequences worth knowing: a URL
naming several levels means the innermost, so only one thing on screen
claims to be the answer; and a link into a **resolved** thread expands it
for reading without reopening it, because reopening is a state change for
everybody (D-128). A stale `?note=999999` marks nothing and opens the deal,
the same answer as no parameter at all.

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
- `grouped_key` rides along unpopulated. It exists now so v3's digest
  batching (§9's "3 new comments on Acme Expansion, not three emails") is a
  query change, not another migration.
- Being handed an opportunity notifies the new owner (`owner_changed`, 3.0a),
  because it is the one access change nobody asked for; the previous owner is
  the actor, so they are not told about their own action.
- Two write routes over the same rows:
  `PATCH /api/v2/notifications/{id}/read` for one and
  `POST /api/v2/notifications/mark-all-read` for everything. The frontend
  inbox panel (`app/NotificationMenu.tsx`) reads the history and marks
  through both.

### Live updates

`GET /api/v2/opportunities/{id}/events` (milestone 3.4) is ADR 0003's stream:
one long-lived `text/event-stream` per open timeline, carrying
**invalidations** and never payloads. The server says
`{"type": "timeline.changed", "opportunity_id": 7}` and the client refetches
through `lib/queries.ts`, so nothing about what a row looks like or who may
read it is decided twice. `app/events.py` is the transport, `routes_events.py`
the permission boundary, `lib/liveUpdates.ts` the client half.

- **Two event types, and one is a superset of the other.**
  `timeline.changed` covers everything hanging off the timeline — entries,
  notes, comments, reactions, a resolved thread — and `opportunity.changed`
  the record, its stage, its sharing, its ownership and its watchers. An
  invalidation may be broader than the write behind it and never narrower, so
  `opportunity.changed` also invalidates the timeline: most writes to a record
  leave a system entry there and the event does not say whether this one did.
- **Publish after `commit()`.** Every `publish_*` call in `routes_*.py` sits
  below the commit, because the subscriber's only reaction is to read again
  and an event sent from inside the transaction sends them to fetch the state
  it is about to replace. A write that wrote nothing publishes nothing — an
  empty `PATCH`, or a version restore of what is already current (D-120).
  `POST /opportunities` is the one write that announces nothing at all: the id
  does not exist until it returns, so there is nobody subscribed to tell.
- **The queue de-duplicates, which is what bounds it.** `_Subscriber.pending`
  refuses an event already waiting, so two writes a millisecond apart are one
  refetch and a slow reader cannot grow the writer's memory. Sound only
  because these are invalidations: idempotent, carrying nothing a dropped
  duplicate would lose.
- **A stream ends by itself** after `settings.sse_max_connection_seconds`
  (300s), having advertised a `retry:`, and the browser's `EventSource`
  reopens it. That is both good SSE hygiene — an intermediary never gets to
  reap a connection this app still believes in — and what makes the route
  testable, since Starlette's `TestClient` buffers a response whole
  (`tests/conftest.py`'s `short_event_streams`). A reconnect is a *gap*, so
  `useLiveUpdates` refetches on every `ready` after the first; the first needs
  nothing, because the screen has only just read the data.
- **Publishing crosses threads on purpose.** A `def` route handler runs in
  FastAPI's worker threadpool while each subscriber's queue belongs to the
  loop serving its own request, so `_Subscriber` stores that loop and
  `publish` hands the work back with `call_soon_threadsafe`. A loop closed in
  between raises `RuntimeError`, which is caught: one reader closing a tab
  must not fail another person's write.
- **`EventSource` does not retry a failed handshake.** A reader with no access
  gets the ordinary 404, which the spec calls a failed connection and forbids
  reestablishing, so the permission answer needs no client handling. What the
  stream never re-checks is a role revoked mid-connection — the reader keeps
  receiving invalidations, and the refetch each one provokes is the read that
  answers 404. No content travels this path either way.

**The note edit guard** is the other half of ADR 0003's conflict model, and
the reason it is last-write-wins rather than CRDTs: comments are immutable and
entries are rarely co-edited, so a note is the one body two people can be
typing into at once. `NoteUpdate` carries a required `updated_at` — the value
the editor was opened against — and `PATCH /api/v2/notes/{id}` answers 409 if
the note has moved. Three things follow:

- It is **required, not optional**: an optional guard is no guard, since the
  client that omits it is exactly the one that clobbers. That makes it the
  one API break this milestone carries (`docs/ROADMAP.md`'s table).
- It is checked **after** the permission check, so a viewer is told they may
  not edit rather than that their copy is stale.
- `app/NoteBlock.tsx` captures `updated_at` **when the editor opens**, not on
  save. The live stream refetches the note underneath an open editor, so
  reading the prop at save time would hand back the value the *other* person's
  write produced and the guard would pass on the one write it exists to stop.
  The refused save keeps the draft and renames Cancel to "Discard my edit",
  which is the "offer to reload" the ADR asks for.
- `lib/api.ts` throws `ApiError` carrying the envelope's `code`, which is what
  `isConflict` reads. That is the first use of a field `errors.py` has always
  emitted for exactly this purpose.

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

### The scheduler

Milestone 6.5 is ADR 0004: APScheduler inside the FastAPI process, started
from `main.py`'s `lifespan` and stopped with it. No broker, no worker
container, no second deploy unit — the ADR's whole argument for a 20-user
single-container app. Revision `0020_job_runs` is the record of what ran.

- **`app/jobs.py` knows nothing about APScheduler** and `app/scheduler.py` is
  the only file that imports it. That is ADR 0004's own instruction ("keep job
  functions free of framework coupling so they stay directly testable") and it
  is why `tests/test_scheduler.py` can call `run_automations` and `run_backup`
  as plain functions — only two of its tests start a scheduler.
- **Two jobs, which is all of v2's recurring work.** `automations` evaluates
  the two of §11's five triggers the clock owns (`TIME_TRIGGERS`) through
  `automations.run_rule` — the same function the manual run route calls, so a
  tick cannot drift from a person pressing Run (D-175). `backup` is ADR 0011's
  `VACUUM INTO`, which has had no schedule since milestone 1.6.
- **Interval triggers, `max_instances=1`, `coalesce=True`.** An interval's
  first firing is one interval away, which keeps a restart loop from taking a
  snapshot per restart and keeps the e2e suite — which boots the real app —
  from meeting a tick. One at a time because two copies would both walk the
  same rules and both act; coalescing because a sleeping process must not wake
  to a queue of missed ticks. Idempotence is what makes a skipped tick safe
  (ADR 0004), not the assumption that missing one is free.
- **`settings.scheduler_enabled` turns it off**, which `conftest.py` does for
  the whole suite: a tick firing mid-test would evaluate a rule the test had
  just written and the failure would land in whichever test ran next.
- **A timer needed more than a schedule** (**D-182**). `no_activity` rate
  limits itself — every action writes a system entry and that entry *is*
  activity, so a nudged deal stops being a candidate until another full window
  of silence has passed. `close_date_approaching` has no such feedback and
  takes `_already_acted_in_window`, with the rule's own `days` as the unit.
  Only applied, non-dry runs count: a preview must not suppress the run it
  previews.
- **Every run is recorded** (**D-183**), written on *start* and updated on
  finish — so a row left at `started` is the signature of a process that died
  mid-job, which a finished-only log cannot show. A failing job records and
  does not raise: there is no caller to answer, and a tick that raised would
  be swallowed by APScheduler's own logging. Read in two places:
  `/api/health`'s `jobs` (the newest row per job, beside `last_backup_at`) and
  `GET /api/v2/job-runs`, which `app/AutomationsPage.tsx` turns into one line
  through `lib/jobs.ts` — because the only place a dead scheduler is *felt* is
  the screen where somebody is wondering why their rule has not fired.
- **One instance is assumed**, as ADR 0004 says explicitly: two would
  double-run every periodic job, since nothing here claims a lock. The same
  assumption ADR 0003's SSE makes, to be revisited together.

### The 14-day rule, and the one thing measurement found slow

Milestone R.3. `AGENTS.md`'s Confirmed Scale — 400 deals, ~200 entries each,
~800,000 rows — is the figure every "no Postgres, no broker" decision was
argued against, and `tests/scale.py` is now the corpus that size (805,220
rows, with shares, sealed entries, tasks and 160,000 notifications).
`tests/test_performance.py` measures every read a person waits on against it,
through the real HTTP stack and as two readers.

Everything was comfortably inside budget except one read, and **the reason was
not the one the plan assumed** (**D-200**): the board's own page took 63 ms
where a deal's timeline took 4 ms. The first hypothesis — the stalled rule
being asked once per row — was wrong, and rewriting it as one grouped pass
measured 55 ms against 56 ms. Profiled, the page's query is **0.3 ms** and the
14-day rule is **55 ms**, because it walks 240,000 note and comment rows
however it is phrased.

- **So the rule stopped being a query** (**D-201**). Revision
  `0022_last_activity` maintains `opportunities.last_activity_at` with
  triggers — the mechanism the FTS index already uses, chosen for the same
  reason: a write path added later cannot forget to call something it never
  knew about. An insert takes `MAX(what is there, the new row)`, which keeps
  bulk loading cheap; an **update** recomputes from the union, which is how a
  soft delete, a restore and an edited `event_timestamp` all arrive. There are
  no DELETE triggers because nothing hard-deletes user data here. The board's
  page is **2.5 ms** now and the whole board **19 ms**.
- **`app/stalled.py` is the single definition** the board, a deal's own screen
  and the dashboard's stalled list all read. `dashboard.py` had carried a
  second copy of the rule since 6.2 and said so in a comment ("One definition
  would be better than two").
- **A stored derived answer needs a test per way it can be wrong.**
  `tests/test_stalled.py` is one case per way the answer can *fall*, each
  confirmed to fail with its trigger disabled — and two of them only became
  real guards after being strengthened, because a note is stamped the same
  second as the deal's own creation entry.
- **D-093 is closed by measurement** (**D-202**): the board keeps filtering
  and sorting in the client. The correctness worry was answered by `fetchAll`
  in 2.9, and moving the predicate into SQL would now save at most 16 ms on a
  read that happens once a visit, while splitting one tested pure function
  across two languages. The cutover point for whoever revisits it is the deal
  count at which the whole list stops being one `fetchAll`.

### Health and backups

**Three probes, three questions** (R.4, **D-203**), all unversioned (D-094):
`/healthz` is liveness and deliberately does no I/O — restarting a process
does not empty a disk, so a liveness probe that reads the database turns a
degraded deployment into a restart loop. `/readyz` is readiness: the same
`BEGIN IMMEDIATE` a real write takes, answered with a **status code**, which
is all a `HEALTHCHECK` reads. The container's healthcheck points there rather
than at `/api/health` as ADR 0011 says, because that endpoint answers 200 with
`database_writable: false` by design — pointed at it, the healthcheck would
call a read-only mount healthy. ADR 0011 item 4 had never actually been
implemented before R.4, though three documents referred to it; the Dockerfile
carries it now and `scripts/docker-smoke.sh` waits for `healthy`, which is the
check whose absence let that sit. The `CMD` also carries
`--timeout-graceful-shutdown 8`, because ADR 0003's streams are held for 300s
and uvicorn waits for in-flight requests — without a bound, every
`docker stop` with a reader attached ended in a SIGKILL.

`GET /api/health` (`main.py`) reports substance, not just liveness (ADR 0011):
`schema_version` (the `alembic_version` row), `database_writable` (a
`BEGIN IMMEDIATE` that immediately rolls back — cheap, and the same lock a real
write would need, so a read-only mount or a full disk is caught before it
becomes a 500 somewhere else), `last_backup_at`, and — since milestone 6.5 —
`jobs`, the newest run of each scheduled job (**D-183**). Opening the connection at
all is inside the same `try`, because `get_connection()` asserts WAL mode,
which is itself a write — a genuinely unwritable database can fail there
before any query runs. That is also why `get_connection()` closes its own
connection when the setup fails (R.4): the caller never receives the object,
so `db_connection`'s `finally` cannot, and with the healthcheck probing every
30 seconds a leak there is a file descriptor every 30 seconds on a deployment
that is already degraded.

`app/backup.py` is `VACUUM INTO`, which snapshots a consistent copy without
locking out writers (unlike copying `app.db`, which can capture a torn WAL
checkpoint). **Uploads are part of a snapshot since R.5** (**D-205**), which
is the other half of ADR 0011 item 2: blobs are content addressed, so
`backups/attachments/` is one mirror holding each digest exactly once rather
than a copy per snapshot, a backup copies in only what is new, and a restore
puts back only what the live tree is missing. The mirror is **never pruned**
while database snapshots are, because an attachment's delete never removes
the file (D-149) and any retained snapshot may reference any digest that has
ever existed. `docs/operations.md` is the volume layout and the procedures,
including the sentence nobody had written down: `backups/` is on the same
volume as the database, which protects against a bad write and not against
losing the disk (**D-206**). `make backup` writes a timestamped snapshot to `backup_dir()`
(default: a `backups/` directory next to the database file — `/data/backups`
under the shipped `DATABASE_URL`) and prunes down to `BACKUP_RETENTION_COUNT`
(default 7). `make restore BACKUP=<path>` reverses it — stop the application
first, since it deletes the live database's `-wal`/`-shm` sidecars before
overwriting `app.db` in place. `tests/test_backup.py` exercises the full
round trip, not just that a snapshot file gets created: ADR 0011 requires the
restore to be "actually exercised," not assumed.

**`make backup` has a schedule since milestone 6.5** — `jobs.run_backup`,
every `backup_interval_hours` (default 24, which is what
`backup_retention_count = 7` always assumed when it kept a week). The gap ADR
0011 carried from milestone 1.6 is closed, and the Makefile target stays for
running one by hand. It was Phase 5's until email moved to v3 (**D-141**); the
scheduler followed Phase 6's automations, which are time-triggered, rather
than following the email work out of the build — so this closed inside v2
rather than after it.

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
- `require_opportunity_owner` — sharing, audit log and version history
  (the member list beside them is `require_opportunity_access`: D-123)

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
  — every access change and every deletion (`opportunity_deleted`,
  `timeline_entry_deleted`, `note_deleted`, `comment_deleted`, the three
  `share_*` actions and, since 3.0a, `owner_changed`).

Any new non-user-initiated write must be traceable to the action that caused it, and
any new delete path needs an audit row. Both, plus the edit history below, are
read together by the activity log (milestone 3.0) — a new mechanism that records
what happened to an opportunity belongs in `app/activity.py` as well.

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
- **A version can be put back** (milestone 3.1c, **D-116**, **D-120**):
  `POST /api/v2/<kind>/{id}/versions/{n}/restore`, owner-only like the read.
  Not to be confused with the `/restore` routes in "Soft deletes and undo",
  which clear a `deleted_at`: these undo an *edit*. `versioning.py`'s
  `apply_version` writes the snapshot back over the parent row —
  `VersionedTable.parent_table` is what keeps that one `UPDATE` rather than
  three — and the route then records a version for having done it, so the
  history only grows and a restore is itself restorable. Three consequences:
  restoring what is already current writes nothing (the server's half of
  D-114, which also makes a retry idempotent), a restored stage writes the
  same `stage_change` system entry any stage change writes, and a restored
  note keeps its `edited` marker and sends no second mention notification.
- The frontend reads all three histories inside the activity log
  (`app/VersionChanges.tsx`, since 3.1c): `lib/domain.ts` declares which
  fields each kind snapshots and how each reads, `versionChanges` compares two
  versions without knowing which kind it holds, and the read hook arrives as a
  prop. That is what keeps a value formatted as money rather than as the
  column's raw text.

### One activity log

The three mechanisms above answer "who did what when" for one opportunity, and
until milestone 3.0 no screen joined them: system entries were read inside the
timeline, audit rows inside the sharing panel, versions one item at a time
(**D-101**, raised by the human at the Phase 2 gate). `GET
/api/v2/opportunities/{id}/activity` is the join, in `app/activity.py`, and it
adds no table — every row it returns already existed.

Milestone 3.1c made it the *only* destination (**D-121**): the per-item
History buttons and the sharing panel's audit disclosure are gone, and an edit
row here opens onto the before/after they used to answer. `GET
/api/v2/opportunities/{id}/audit-log` and the three `GET .../versions` reads
all remain — what moved is where a person reads them.

**The button is labelled "Activity"** and the dialog "Activity and history".
It shipped as "History" — which is what the buttons 3.1c *removed* were
called, so the Phase 3 reviewer opened the one that was left, found a feed
rather than a version history, and reported that the consolidation had never
happened (**D-136** finding 1, fixed in milestone 3.7). The two lessons are
worth keeping together: a consolidation that reuses the removed thing's name
reads as the removed thing, and the only way that was ever going to surface
is a person meeting the screen cold.

- **A row keeps the visibility of the source it came from.** System entries go
  to anyone with access, because they are already on the timeline; audit rows
  and version rows stay owner-only (`AGENTS.md` invariant 7, D-096). So the
  route is `require_opportunity_access` and the *rows* are what the role
  decides — an editor asking what happened gets the events they may read
  rather than a 403. Widening that (showing a non-owner that an edit
  happened, which an edit marker already says) is **D-102**, left for the
  human.
- **An event appears once.** An access change — sharing, or an ownership
  transfer — writes both a system entry and an audit row, so `ACCESS_ACTIONS`
  is dropped from the feed and the audit log endpoint keeps them. An opportunity edit reaches the feed only if it moved a field
  other than `stage`, because a stage change already writes its own system
  entry. Version 1 is excluded everywhere by the join to the preceding
  version — it is the creation baseline, not an edit (D-097).
- **The route answers oldest-first; the reader sees newest-first** (3.8). The
  timeline beside it defaults to newest-first (D-137), so the two histories of
  one deal used to disagree about which end was the present. `useActivity`
  reverses the list `fetchAll` has already read whole — the route stays
  oldest-first because it is keyset-paginated and because an audit log is
  oldest-first for the same reason a log file is, and reversing five merged
  keyset queries would mean reversing each comparison as well as each
  `ORDER BY` for a feed never read a page at a time.
- **The id is `rank * ACTIVITY_STRIDE + source row id`**, five id spaces held
  a trillion apart, in the spirit of `search.py`'s FTS5 rowid. The rank leads
  because it is also the tie-break: every timestamp is second-resolution
  (D-067), so one action's rows share one, and ranking system entry → version
  → audit row reads them back in the order that action performed them.
- **Five queries merged in Python, not one `UNION`.** The branches share only
  actor and time. Each is asked for `limit + 1` rows past the cursor, which is
  exactly enough for the merged page to be exact, and the whole feed is read
  through `fetchAll` into `app/ActivityDialog.tsx` — one Modal, one sentence
  per row from `lib/activity.ts`, which is to this what `lib/notifications.ts`
  is to the inbox. `lib/domain.ts`'s `VersionField.field` is what keeps the
  sentence's field names and the expanded row's labels the same words.
- **An edit row opens, and offers the way back without being opened** (3.1c,
  amended by 3.7). The disclosure fetches that item's versions when it is
  clicked, not when the feed is drawn, and renders version N against N − 1
  through `app/VersionChanges.tsx`. **Restore sits on the row beside that
  disclosure**, not inside it: which version it puts back is
  `version_number - 1`, arithmetic on a field the feed row already carries, so
  nothing about the control needed the read — and two levels of depth were
  enough to make the reviewer report restore as absent altogether (D-136
  finding 2). It offers the version the edit *replaced*, which is how every
  recorded version except the current one is reachable exactly once —
  including version 1, the state the thing was created in. An edit row only
  ever reaches an owner, so the control needs no second permission check of
  its own.

A comment being posted is the one event no mechanism records (comments are
immutable, so they have no version table); its deletion is in the audit half.
Resolving a thread (3.3) is not recorded here either: it is read where it
happened, on the thread, which names who closed it and when — and putting it
in the audit log would widen `AGENTS.md` invariant 7 past deletions and
sharing (**D-128**).

### The bulk action bar

`docs/UX.md` names five actions over a selection — change stage, assign owner,
add to view, export, delete. Milestone 2.4c shipped the two that already
existed one id at a time and **D-070** deferred the rest; milestone 3.0a built
them. What is worth knowing is that they are gated by three different rules,
because they write to three different things:

- **Change stage, assign owner and delete write to the opportunity**, so they
  are owner-only per id through `require_opportunity_owner`, and
  `BulkActionBar` disables them unless `canManageOpportunity` holds for the
  whole selection.
- **Add to view writes to the caller's own saved view**, so its per-id rule is
  only `require_opportunity_access` (**D-106**): anything the reader can see
  can be pinned into a list of their own.
- **Export reads**, so it is not an action on `POST /api/v2/opportunities/bulk`
  at all — that endpoint answers `{"results": [...]}` per id and a file has no
  room for per-item outcomes. It is `GET
  /api/v2/opportunities/export/{csv,json}?ids=`, a plain link like the three on
  an opportunity's own screen, permission-filtered inside the query the way
  search is, and its rows are the opportunity's own fields rather than each
  deal's whole timeline (**D-107**). PDF is deliberately not among them.

Two whole-request failures are raised before the loop, because they are wrong
about the request rather than about one id: an `assign_owner` naming an email
nobody uses, and an `add_to_view` naming a view that is not the caller's.

**An ownership transfer leaves the previous owner behind as an editor**
(**D-105**). It is the one action with no undo available to the person who
performs it, so a mis-typed handover does not remove the deal from their board;
the new owner can drop that share from the sharing panel. It is recorded the
way sharing is — a system entry, an owner-only `owner_changed` audit row, and a
notification to the new owner — and writes no version row, because `owner_id`
is not one of `OPPORTUNITY_VERSIONS`' fields. `app/share_utils.py` is the one
place a share row is granted, shared with `create_share`, because both have to
cope with a soft-deleted row under a unique index.

### The composer

Milestone 3.1 replaced every place a person writes content — an entry's body, a
note, an edit to a note, a comment — with one TipTap editor whose storage is
Markdown. `docs/FEATURES.md` §4 is the spec and **no content migrated**, which
is the whole reason Markdown was chosen over ProseMirror JSON: these bodies
have been Markdown text since the MVP, so this is a new way to type what was
already stored. It is entirely frontend; no route, schema or table changed.

- **`lib/markdown.ts` declares the node set, and it is the renderer's**
  (**D-108**). `contentExtensions` is what the editor may produce *and* what
  `app/MarkdownText.tsx` can render, so a document cannot be written and then
  not read back: `underline` is off because Markdown has no syntax for it and
  the sanitizer has no `u` tag. The conversion is TipTap's own
  `@tiptap/markdown` through a standalone `MarkdownManager`, so
  `markdownFromDoc` — the function the component calls on every keystroke — is
  the one the unit suite tests without a DOM. `linkProtocols` lives here and is
  read by both the editor's link validation and the sanitizer's `href`
  allowlist: **sanitization on render is still the boundary**, and sharing the
  list is what stops the editor producing a `javascript:` link that the
  renderer would silently strip. The sanitizer's allowlist is otherwise
  unchanged, which is what `FEATURES.md` §4 requires.
- **`app/RichTextEditor.tsx` holds two shapes**, the way `InlineEdit.tsx` does.
  `RichTextEditor` is the editor itself: uncontrolled like the `<textarea>` it
  replaced (`value` seeds the document once; every keystroke reports Markdown
  through `onChange`), named by `aria-label` with `role="textbox"` because a
  contenteditable `div` cannot be a `<label>`'s target, and focusing itself on
  open — ProseMirror creates the editable element in a layout effect, one
  render after `useInlineEditor` would look for it. `Composer` is the same
  editor collapsed to the control that opens it (**D-110**, `docs/UX.md`'s
  progressive disclosure): a timeline is made of composers and each open one is
  a ProseMirror view, the draft lives in the `Composer` so `Esc` and Cancel
  keep it, and posting unmounts the editor rather than clearing it.
- **The whole timeline panel is disclosures now** (milestone 3.7). The entry
  composer was the one writing surface that stood permanently open: 400px of
  form, under a 144px filter bar, which put the first timeline entry 930px
  down a 1000px viewport — so a reader opening a deal met its controls rather
  than its history (**D-136** finding 3; measured at 393px after). Both are
  collapsed behind a trigger: `New entry`, and `Filter and order`.
  `OpportunityPanel` drives the composer through `useInlineEditor`, the same
  hook and the same focus rule as every other editor that replaces its own
  control, so Cancel puts the reader back on the trigger. Two consequences
  worth knowing: `TimelineEntryForm` renders Cancel unconditionally now
  (closing without posting is a thing in both modes), and `c` opens the
  composer as well as focusing it.
- **The filter bar says what is in force while it is shut** — the reading
  order in the same words as the control that sets it, plus a count of
  anything else applied (`lib/domain.ts`'s `timelineFiltersApplied`). It also
  opens itself when a non-default filter arrives, which is the answer to
  **D-137**: `timeline.order` is linkable view state on purpose, so a stale
  `?timeline.order=asc` in an old tab legitimately reverses the timeline — the
  bug was that nothing on screen said so, and two readers comparing screens
  had no way to find out why they differed (D-136 finding 5).
- **The toolbar carries only what needs no second question.** Bold, italic,
  strike, code, the three lists and quote; a link and a heading are typed
  (`[text](url)`, `### `) because a button for either has to open a dialog out
  of a composer. It is named "Formatting", not after the field — a group called
  "Formatting: Body" is also a match for a query for "Body".
- **An edit that changed nothing writes nothing** (**D-114**): the editor
  normalizes syntax, so `NoteBlock.save` compares the draft against
  `normalizeMarkdown(note.body)` rather than the raw text — otherwise reopening
  a note and pressing Save writes a version row and an edit marker for an edit
  nobody made.
- **Entry bodies are Markdown too** (**D-109**). They used to print as plain
  text, so a list typed into the one field a call gets logged into showed its
  dashes.
- **Two things about testing it.** `userEvent.type` cannot drive ProseMirror
  under jsdom (it applies a typed character by reading back the DOM mutation a
  browser would have made), so `app/test-editor.ts`'s `writeInEditor` pastes
  instead — a real action, no seam in the component — and `clearEditor` deletes
  a selection, which is a ProseMirror command (**D-113**). Typing itself, and
  with it the Markdown input rules, is `e2e/18-rich-text.spec.ts` and
  `e2e/19-suggestions.spec.ts`. `vitest.setup.ts` stubs the geometry
  ProseMirror asks for, for the same reason the virtualizer needed
  `offsetHeight`.

### The three typed triggers

Milestone 3.2 is `@`, `/` and `#` in that composer: who to notify, which block
to start, which earlier entry to point at. They are one mechanism —
a `@tiptap/suggestion` plugin per character, one menu, one keyboard rule
(**D-111**, which is why 3.1 shipped none of them) — declared as data in
`lib/suggestions.ts` and rendered by `app/Suggestions.tsx`. `docs/FEATURES.md`
§7 is the requirement: mentions needed a full email address typed from memory,
which made requirement 13 effectively undiscoverable.

- **A mention is still plain `@email` text** (**D-122**), so nothing about
  storage, the renderer or `notification_service.MENTION_RE` changed. The
  autocomplete types the address a person could not remember; it does not
  introduce a node the sanitizer has never seen.
- **Who it offers comes from one new read**, `GET
  /api/v2/opportunities/{id}/members` — the owner *and* every share, which is
  the set a mention can actually reach, and open to every role rather than to
  the owner (**D-123**): a viewer writing a comment mentions the same people.
  What stays owner-only is the grant itself, `GET .../shares`, which carries
  who invited whom and when.
- **The slash menu is the blocks, not the marks.** The toolbar already carries
  bold through quote; this carries what a reader would otherwise have to know a
  Markdown input rule for — a heading, a code block, a divider. Every item is a
  command over a node `lib/markdown.ts` declares, so the menu cannot write a
  block `MarkdownText` will not render.
- **A link to an entry is a relative Markdown link** (**D-124**):
  `[title](/opportunities/3?entry=17)`. The href needs no protocol so the
  sanitizer keeps it unchanged, `app/MarkdownText.tsx` renders a same-app href
  as a router `Link` rather than reloading the SPA, and `OpportunityPanel`
  reads `?entry=` to scroll that card into view and mark it
  (`.timeline-entry.is-linked`). It is not a filter, so it is not part of
  `TimelineFilters` and carries no `timeline.` prefix.
- **The editable keeps focus throughout.** The menu is a `listbox` the
  editable points at with `aria-activedescendant` — set on `editor.view.dom` in
  an effect, because `editorProps.attributes` is read once at creation — driven
  by the arrow keys the plugin hands over, and a mouse choice is taken on
  `mousedown` with the default prevented. `Escape` closes the menu and stops
  there: the native event's propagation is stopped so the `Composer` behind it
  does not also close and lose the draft.
- **The plugins are built once and read a ref.** Rebuilding the extension list
  when the member list arrives would rebuild the editor and throw away the
  document under the cursor. That is also the one place in the frontend with an
  `eslint-disable` for `react-hooks/refs`: the closures are plugin callbacks,
  nothing in them runs during a render, and the two alternatives are worse
  (see the comment, and **D-125**).

### Threaded comments

Milestone 3.3 gave a note's comments two things `docs/FEATURES.md` §7 asks
for: a reply that is visibly an answer, and a way to say the discussion is
over. Revision `20260924_0007_comment_threads` adds three columns to
`comments` — `parent_id`, `resolved_at`, `resolved_by` — and no table.

- **One level, enforced in the route.** A reply's parent must itself be a
  thread root and must be on the same note; anything else is a 400 or a 404
  rather than a silent reparenting (**D-127**). The column could hold a
  deeper tree and the API will not write one: a discussion that indents four
  times is the unreadable thing resolve exists to prevent, and depth is the
  cheapest thing to add later if it is ever wanted.
- **The read shape is the thread.** `CommentThread` is `CommentPublic` plus
  the resolved pair and `replies`, so `NotePublic.comments` is a list of
  threads and a reply is never a top-level row. `threads_from_rows` groups
  one flat, chronological query — a reply cannot precede the root it names,
  so one pass in that order is enough. Writing a comment still answers with
  the single `CommentPublic` that was written.
- **Resolving is author-or-owner** (**D-128**), the rule that decides who may
  change any existing timeline item (D-005), resolved through
  `require_edit_permission` like the rest. It is `POST .../resolve` and
  `POST .../unresolve` rather than a PATCH, because a comment PATCH is the
  route `AGENTS.md` invariant 2 says must not exist — and resolving changes
  no `body`. Both directions are idempotent, so the first resolver is the one
  recorded and a retry is safe.
- **A thread is a level of the delete cascade.** `soft_delete_comment` stamps
  the replies with the root's own `deleted_at` and `restore_comment` brings
  back exactly that stamp, so one Undo restores the thread and a reply
  deleted separately stays deleted (D-067). A reply whose root is deleted
  cannot be restored alone — `fetch_deleted_comment_context` refuses it, the
  same answer a note under a deleted entry gets.
- **A reply notifies two people at most.** `notify_note_comment` takes a set
  since 3.3 — the note's author and the author of the comment being answered
  — and when they are the same person that is one notification, not two.
- **The frontend draws a thread, not a list** (`app/CommentThread.tsx`).
  Reply sits on the thread rather than on each message, because a control on
  a reply would ask for what the API refuses; a resolved thread collapses to
  "Resolved by <name>" with Show beside it, which is reading rather than
  reopening. Resolve is not optimistic (`useResolveThread`): what the reader
  is shown is a name the cache does not hold.

### More than one person on a task

Milestone 4.6, the other half of the "build both" ruling (**D-163**).
`task_assignees` (revision `20261009_0014_task_assignees`) is the truth; the
API answers with `assignees` and takes `assignee_emails`, and
`tasks.assignee_id` is **frozen** — unread from 4.6, dropped in Phase 6 beside
`follow_up_date`.

- **The version snapshot records a set.** `task_versions.assignee_ids` holds
  the canonical string `routes_tasks.TASK_ROWS_SQL` produces — ids ascending,
  comma separated — because `versioning.version_is_current` compares snapshots
  *as strings*, so two recordings of the same people must spell them the same
  way or restoring would never be a no-op (D-120). A version written before
  this revision keeps its single `assignee_id` and reads as a one-person list
  (D-097).
- **`apply_version` writes columns, and this one is a table.**
  `VersionedTable.applied_fields` is the exception that says so, and
  `restore_task_version` puts the set back itself. It is the first bend in the
  one-shape-for-four-histories abstraction; bending it at the edge was cheaper
  than widening the `UPDATE` every other restore pays for.
- **D-142 now reads "any assignee may close it."** A shared task is done when
  whoever got to it says so; requiring all of them is an approval workflow
  `FEATURES.md` §8 rules out. Editing stays author-or-owner (D-005).
- **My Tasks is a membership test** (`EXISTS` against `task_assignees`, served
  by `idx_task_assignees_user`) rather than a column match.
- **An assignment is toggle state, not content**: `set_assignees` writes an
  ordinary `DELETE FROM`, the reasoning `soft_delete.py` applies to
  `reactions` and `watchers` (D-130). Who *used* to owe a task is in
  `task_versions`, which is the history that matters.
- **A frozen column is a hazard while anything still reads it.** 4.5's
  task-comment notification read `tasks.assignee_id`, so 4.6 silently stopped
  telling assignees; the backend test passed because it never covered an
  assignee who is not the author, and `e2e/24-tasks.spec.ts` is what failed.
  Grep every reader when a column is retired.

### A task's discussion

Milestone 4.5, built on the human's "build both" ruling that overruled D-146.
`task_comments` (revision `20261004_0013_task_comments`) is a **flat,
chronological log** on a task — body, author, time, `deleted_at`.

- **A second table rather than `comments`** (**D-162**). `comments.note_id` is
  assumed in 17 places across 7 modules, two of them the search queries, which
  answer with a non-nullable `SearchResultPublic.entry_id` that a task comment
  cannot have. Reusing it meant breaking a shipped read or leaving task
  comments unsearchable; mirroring 3.3's threads was more than was asked for.
  Threading stays additive — the three columns revision 0007 added to
  `comments`.
- **Immutable, like every other comment here** (invariant 2): no PATCH, so no
  `updated_at`, no `edited` marker and no version table. Delete is the only
  change one can undergo, and it is soft, audited
  (`task_comment_deleted`/`task_comment_restored`) and undoable.
- **It rides along with the task** (`routes_tasks.comments_by_task_id`), the
  shape a note's comments have; the writes that answer with a task still answer
  with the row they changed and the client refetches.
- **A task has a cascade now.** 4.1's delete was the one helper in
  `soft_delete.py` with nothing under it, because §8 rules out subtasks; a
  comment is readable only through its task, so it goes with the task and with
  the deal, scoped by the delete's stamp.
- **Its notification is its own type** (`task_comment`), because it goes to the
  two people the task is about — author and assignee, as a set — rather than to
  everyone on the deal the way `shared_activity` does.
- `app/TaskDiscussion.tsx` draws it inside the deal's task panel only: `/tasks`
  is a to-do list, not a place to catch up on discussion.

### Reactions and watchers

Milestone 3.3a, the other half of the roadmap's single "threaded comments
with reactions ... watchers" line that 3.3 split off (**D-126**). Two new
tables from revision `20260925_0008_reactions_watchers`, unrelated to each
other beyond both being toggle state rather than content.

- **A reaction** is one row per (comment, person, emoji) against a fixed
  seven-item set, attaching to a thread root or a reply alike.
  `INSERT OR IGNORE` on the `(comment_id, user_id, emoji)` unique index makes
  reacting twice a no-op, so both routes answer 200. Any role that may write
  the timeline may react — unlike resolve this is not the author-or-owner
  rule (D-005), because a reaction changes nothing about what anyone wrote.
- **A watcher is the one deliberate exception to "absence of access is a
  404"** (**D-129**). `docs/FEATURES.md` §7 names "follow an opportunity you
  are not shared on," which the ordinary role-resolving gate cannot answer —
  it would 404 exactly the caller the feature exists for. The three
  `.../watch` routes and nothing else use `require_opportunity_exists`
  (`permissions.py`) — presence only, no role — so any authenticated caller
  learns whether an id is live, and nothing more: watching grants no read
  access, and `GET .../watchers` (who is watching) stays owner-only through
  the ordinary `require_opportunity_owner`, the same visibility rule as the
  share list beside it. A watcher is unioned into `notify_shared_activity`'s
  recipients (`notification_service.get_watcher_user_ids`), additive to
  whoever already gets told, never a narrower filter over them.
- **Neither table is soft-deleted** (**D-130**). A reaction or a watch is "I
  am currently doing this," toggle state a person sets and unsets, the same
  reasoning `soft_delete.py` already applies to `sessions` — not content
  whose history is worth keeping. Both routes write ordinary `DELETE FROM`,
  and `tests/test_soft_delete.py`'s hard-delete scanner is expected to leave
  `reactions` and `watchers` alone. Removing a reaction or unwatching returns
  the resulting state (200, not 204) — unlike `delete_comment` or removing a
  share, there is a remaining state (a count, a boolean) the caller needs
  immediately to settle the toggle in the UI.
- **The frontend.** `ReactionBar` (`app/CommentThread.tsx`) shows the emoji
  already in use as count pills, with a "React" trigger revealing the fixed
  set behind progressive disclosure. `WatchToggle` (`app/OpportunityPanel.tsx`)
  is reachable from the "This opportunity is not available." screen itself —
  the one place watching-with-no-access has anywhere to render, since there
  is no separate discovery UI for a deal's id. `SharingPanel` gains a
  read-only "Watching" list, shown only when non-empty.

### Attachments

Milestone 4.3 is ADR 0008 and `docs/FEATURES.md` §6: the documents a deal
turns on, which lived in somebody's inbox until now. Revision
`20261001_0012_attachments` adds one table and four routes
(`routes_attachments.py`), and `app/uploads.py` — written in Phase F before
any endpoint accepted a file — is what they are wired into.

- **A file hangs off a timeline entry**, as `attachments.entry_id` rather than
  ADR 0008's `entity_type`/`entity_id` pair (**D-148**). `docs/ROADMAP.md` is
  explicit that "proposals and contracts attach to the entry they belong to",
  and one parent as a key keeps the foreign key, the index and the
  one-statement soft-delete cascade a polymorphic parent gives up. The ADR
  carries an amendment section recording that and the four decisions below.
- **The row's `sha256` is where the file is**, not a checksum beside a path:
  `uploads.resolve_stored_path` turns it into `{root}/{sha256[:2]}/{sha256}`
  under `uploads.attachments_dir()` (`attachments/` beside the database file,
  the shape `backup.backup_dir()` already uses). Content addressing
  **replaced F.5's random generated name** (**D-147**) because the digest also
  deduplicates: two rows with one digest are two attachments and one file, so
  the table carries no unique index on it. Containment is two independent
  checks — the 64-hex-character pattern before the filesystem sees anything,
  and the resolved parent *and shard name* afterwards, which is what catches a
  symlinked `ab/` planted in the root.
- **Sniffing is the allowlist; the filename is metadata.** `validate_upload`
  never consults what the client declared, which is what makes a `.exe`
  renamed `.pdf` a 415. Word, Excel and PowerPoint are on the list
  (**D-150**) because that is what contracts arrive as; they share one zip
  signature, so `_sniff_ooxml` separates them by the part prefix in the
  archive's central directory and refuses any archive carrying a
  `vbaProject.bin`. `safe_filename` keeps only the last path segment, for the
  readers of the name rather than for containment.
- **An entry's files travel with the entry.** There is no list route:
  `TimelineEntryPublic.attachments` is filled by
  `attachment_utils.attachments_by_entry_id`, one query for a whole page, the
  shape `reactions_by_comment_id` already uses. The three writes that answer
  with an entry send `[]` like they do for `notes`.
- **A download is a read of the opportunity** —
  `GET /api/v2/attachments/{id}/download`, `require_opportunity_access`, so a
  viewer may — and it is the only way bytes leave the volume, since `/data` is
  never a static path. `uploads.download_headers` forces the download and
  sets `nosniff`; the digest in the payload is not a capability, because the
  route resolves the row the id names and reads the digest from it. A file the
  volume has lost answers 404 rather than failing mid-response — still a real
  state, but a recoverable one since R.5: a restore copies back any blob the
  live tree is missing (**D-205**), and `tests/test_backup.py` loses one on
  purpose to prove it.
- **Deleting one never removes the file** (**D-149**). The row is soft,
  audited (`attachment_deleted`/`attachment_restored`) and undoable, and the
  only safe prune predicate has to consider a soft-deleted row and a restorable
  backup — so nothing prunes in v2. It is also a level of two cascades, the
  entry's and the deal's, unlike a task, which outlives the entry that
  prompted it.
- **No version table and nothing in the AI context.** An attachment has no
  editable field, so invariant 8 has nothing to keep; a filename is
  attacker-controlled text, so it stays out of the model's context (**D-151**)
  and invariant 4's "attachment" clause is satisfied by there being nothing
  there to label. It is not searchable either (**D-152**), which leaves ADR
  0007's four-kind rowid ceiling untouched — and is why `SearchKind` is now
  split from `SourceType`, since a notification can be about an attachment and
  a search result cannot.
- **The export lists them, and does not include them** (milestone 4.4,
  placement settled by **D-164**): `export_service.render_entry_attachments`
  puts each file under the entry it belongs to — filename, size, uploader —
  absent on an entry with none, with the count in the summary and one sentence
  there saying they are listed rather than included. It was a single section at
  the end until the human read a real export and said otherwise; D-154 records
  the argument for the end, which the summary count now answers more cheaply. All three formats carry the files (**D-155**),
  because one read feeds them: the JSON gains `attachments` per entry and the
  CSV a `row_type: attachment` with three appended columns. `fetch_export_data`
  reads them through `attachment_utils`, so the export cannot disagree with the
  screen about which files a deal has, or about `deleted_at`.
- **A file is attached in two places on purpose** (4.3a, **D-161**):
  `TimelineEntryForm` carries *Attach a file (optional)* for the document that
  is already to hand while the entry is being written, and the card's own
  trigger takes the one that arrives later. The form's path is two requests in
  order — the entry has to exist first — so a refused file leaves a saved entry
  and an open form that says so, with the created id held in state so a retry
  retries the upload rather than posting a second entry. A **system entry**
  offers no trigger at all, the way it offers no Edit or Delete.
- **The frontend** is `app/AttachmentList.tsx` on the entry card, between what
  happened and what was said about it. The picker is collapsed behind "Attach
  file" (`useInlineEditor`), the delete is optimistic with Undo (2.4b), the
  upload is not optimistic because the server decides the type and the size,
  and the download is a plain link. `lib/api.ts` omits its JSON content type
  for a `FormData` body — the one request in the app that is not JSON, because
  the multipart boundary is the browser's to generate.

### Editing where content is read

`AGENTS.md` v2 scope item 12 — "content is edited where it is read, not in a
form elsewhere on the page" — is milestone 2.11, and it is entirely frontend:
the routes it writes through already took a partial `PATCH` (2.10 is what
made every one of those writes keep a version). Before it, editing an entry
loaded it into the composer at the top of the panel, so a reader fifty entries
down was moved to the top of the page (**D-051**).

`app/InlineEdit.tsx` holds both shapes, and a fourth editable surface should
use one of them rather than a third:

- `useInlineEditor(triggerRef, editorRef)` is the open/close state and the
  focus rule, for anything that draws its own editor: a timeline entry swaps
  its card body for `TimelineEntryForm` (`app/TimelineEntryList.tsx`), a note
  swaps its rendered Markdown for a textarea (`app/NoteBlock.tsx`). Focus
  moves into the editor when it opens and back to the control that opened it
  when it closes — both in one effect, after the render that swapped the
  views, because in each direction the element to focus does not exist yet
  when the handler asks for it. The refs are the caller's and passed in: a ref
  handed back from a hook and then read in JSX is a ref accessed during render
  as far as the React Compiler's lint rule can tell.
- `InlineEdit` is one field, drawn as its own value and replaced in place by a
  control. `OpportunityField` binds it to `lib/domain.ts`'s
  `editableOpportunityFields`, which is where a field's label, its editor, how
  it reads and what it patches are declared once — so a field cannot be
  editable as a table cell and not on the heading, or send a different patch
  from each.

Four things about it are load bearing:

- **The trigger is named by its value, not by "Edit"** — the action rides on
  `title`. An `aria-label` would override name-from-content, and this control
  sits inside the opportunity's `h2`: labelling it "Edit Opportunity" renames
  the heading to that, which `e2e/helpers.ts`'s `openTimeline` caught. Tests
  address it by `getByTitle`, which also survives the value being edited.
- **Every write is one partial `PATCH`.** `useEditOpportunity` replaced
  `useChangeOpportunityStage` and is now the single optimistic partial write:
  a card dragged to another column, the move-to-stage select, `[`/`]`, a table
  cell and a heading field all send only the key that changed.
  `useOpportunityFieldSave` is the one place that write is paired with a
  toast, called once per view rather than once per cell.
- **What the API would refuse is refused before the optimistic write.** The
  same three rules `OpportunityUpdate` carries — a non-empty name, a
  non-negative number, a close date that may be cleared to `null`. An editor
  that closes and then silently reverts is worse than one that stays open and
  says why.
- **Two surfaces, deliberately, not five** (**D-099**). The table grid and the
  opportunity's own heading are where a field is read *as a field*; a board or
  list card reads a deal, and an edit affordance on every value there is the
  clutter `AGENTS.md`'s Design bar rules out. The row's name stays a link to
  its timeline, where the heading edits it. Comments remain immutable
  (invariant 2) and a system entry has no editor (it cannot be edited through
  the API either).

### Keeping something to yourself

Milestone R.1b, the human's ask and their "build both" ruling (**D-193**).
Two shapes, deliberately different in kind.

**A sealed entry.** `timeline_entries.visibility` (revision
`0021_entry_visibility`) is `shared` or `private`, and private is readable by
its author alone — **not by the opportunity's owner** (**D-194**): "private
unless the owner asks" is not private, and the symmetric rule is what makes
this one predicate rather than a role lookup.

- **The row stays; the content goes.** A colleague's timeline still holds the
  entry, with its number, its author and its time, and nothing else.
  `routes_timeline.entry_from_row` is where it is emptied — one function that
  every read of an entry passes through, rather than a predicate each of the
  four reads has to remember.
- **`permissions.VISIBLE_ENTRIES_SQL` is the rule**, and it is deliberately
  *not* inside `timeline_utils.ENTRY_SEQUENCE_SQL`. An entry's number is a
  property of the deal: putting it there would renumber one reader's timeline
  against another's, and the AI cites those numbers.
  `test_a_sealed_entry_keeps_its_number_for_everyone` is what fails if anybody
  moves it.
- **Every read that could leak one was changed**: the timeline list, the six
  context fetchers that resolve the parent of a note, a comment or a reaction
  (so every write on a sealed entry answers 404), all four branches of the
  search query, the AI's context — now per reader, which is the one place a
  leak would be invisible — the export, the attachment download, and the title
  a task shows for the entry it came from.
- **Sealing afterwards withdraws what the entry already said** (**D-195**). A
  notification is a copy carrying the title, written at the time and read
  without re-checking the deal, so `notification_service.withdraw_entry_
  notifications` soft-deletes those rows and the inbox stops serving them.
  Unsealing does not put them back: readable again is not news again.
- **A private entry notifies nobody and triggers no automation** when written.
  A rule acts with its creator's authority (D-173), and an entry its creator
  may not read is not something they could have done by hand.
- **A new entry is private by default** (**D-196**), with a tick box to reveal
  it, as asked — `schemas.DEFAULT_ENTRY_VISIBILITY` is the one constant, and
  the test suites now say which visibility they mean rather than inheriting it.
  The author's own card carries the same `Private` badge the sealed card
  shows a colleague: without it, the only thing telling the author which of
  their entries is sealed is the verb on a button (`Reveal` against `Keep
  private`), which is a difference nobody reads while scrolling.

**A notebook of one's own.** `private_notes` is one row per person per deal:
the running note that is not a record of anything that happened, so it is not
in the deal's history at all. `routes_private_notes.py` is the only module that
mentions the table — a grep for it is the whole audit — and both routes resolve
the row by `(opportunity_id, user_id)`, so there is no id a caller could supply
that reaches somebody else's. Any role may keep one, including a viewer: a note
about a deal is a fact about its reader rather than a write to the record.

### Soft deletes and undo

Nothing is hard-deleted. `soft_delete.py` is the only place user data is deleted:
it stamps `deleted_at` and cascades it down the opportunity → entry → note →
comment → reply tree (the last level since 3.3), and every read query filters
`deleted_at IS NULL` at each level.
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

**The context labels what a person wrote** (milestone 4.7, **D-166**). It is
line-oriented plain text, so a body containing `Author: System` on its own
line used to forge one of this app's own structural lines — invariant 4's
"labelled everywhere" was true of nothing. Two shapes, because there are two
kinds of field: a **body** (entry, note, comment) is fenced between
`[BEGIN USER TEXT <token>]` and `[END USER TEXT <token>]`, and a value that
sits *on* a structural line (a title, an author name, a filename) is
**flattened to one line**, which no fence can do for it. The token is drawn
per request — a fixed marker is a string somebody can type into a note.
Attachments are in the context by name, size and uploader, and the prompt says
the model cannot read what is inside them — and, since the Phase 4 review
(**D-169**), that it must *say so plainly* when asked what a file contains.
Obeying the prohibition and disclosing it turned out to be two different
things: asked to summarize a PDF, the model answered from the timeline under
the reader's own word "document" and invented nothing, but never mentioned it
had not opened the file. What this makes unforgeable is the
*structure*; obedience to the instruction is the model's, and
`conftest.no_live_network` forbids the only call that would prove it, so the
suite asserts the mechanism and a human checks compliance.

Read-only by construction, not by prompt instruction, in two independent ways.
`routes_ai` opens `database.read_only_connection()` — `PRAGMA query_only = ON`, so
SQLite itself raises on any write from that path, and it is a pragma rather than a
`mode=ro` URI because the database runs in WAL. It then assembles the full
chronological timeline as text (`ai_service.build_timeline_context`), sends it with
the question via `client.responses.create(..., store=False)`, and returns a string.
No tool surface is exposed to the model, and none should be added. The context
names every entry as `[Entry #<number>, <timestamp>]`, which is why a timeline
card prints `#<number>` in its meta row since milestone 3.8: the model cited a
number the screen did not show, so an answer referred to something the reader
could not find. That number is a **per-deal sequence** (3.9, **D-139**) — #1 is
the oldest thing that happened on the deal — and both sides read one
expression, `timeline_utils.ENTRY_SEQUENCE_SQL`, rather than each counting for
itself. `tests/test_ai.py::test_the_context_cites_the_numbers_the_timeline_prints`
is what fails if they drift. `AiAskResponse.referenced_entry_numbers` is the
same numbering (renamed from `referenced_entry_ids` by **D-140**, which is the
defect a real model call found and the context test could not: the field kept a
cited `#N` only if `N` was a valid row id, so it was validating one numbering
against another). It is a reading aid and not an identity: a
backdated insert renumbers what follows, and the row id is what `?entry=`
links carry. Making the model emit `?entry=` links instead (D-124's shape, which
`app/MarkdownText.tsx` already renders as a router `Link`) is Phase 4 work,
with the attachment citations. Both halves are
pinned by `test_invariant_*` tests. Viewers may ask
questions; the endpoint uses `require_opportunity_access`, not
`require_timeline_write`.

**Where it lives on screen changed in R.1** (**D-189**): the panel was the
first thing in the deal's right-hand rail, so one long answer pushed the
record and the deal's tasks two screens down — the 6.4 review's report. It is
a **drawer now**, opened from the record header's *Ask* and closed from its
own, and it opens into a third column that narrows the timeline and never the
rail. `AiSidebar` takes an `onClose` and is the same component either way.
6.5a's cap on the panel's height stays: it is what keeps the ask box on screen
once the panel is tall, and it was never the answer to what the rail beneath
it was doing.

**A failure says which kind it is** (R.1, **D-192**, closing D-052).
`classify_ai_failure` matches the SDK exception's class *name* — so it
survives an SDK reorganization and a test can raise a stand-in rather than
construct an `httpx` response — and answers 503 for anything an operator
fixes (rejected credentials, an unknown model, a missing permission), 504 or
502 for a timeout or an unreachable service, and 400 for a request the
provider refused. The sentence names `OPENAI_MODEL` or `OPENAI_API_KEY` and
never their values, the provider's own wording or the model it tried; that
goes to the log.

**Three things were added in milestone 6.4**, all of them reads:

- **The answer streams.** `POST .../ai/ask/stream` answers
  `text/event-stream` — a different shape from ADR 0003's live updates
  (**D-187**), because that one is a GET carrying invalidations and this one
  needs the question in a body and carries content. `delta` as the answer is
  written, `done` with the citations, which are computed from the finished
  text. A failure mid-stream is an `error` event, not a 502: the status line
  is long gone. A refusal is still an ordinary 404, because the permission
  check runs before the response starts. `lib/aiStream.ts` is the client
  half and deliberately not `apiRequest`, which reads a JSON body and throws
  on non-2xx.
- **A summary can be scoped to dates**, and **the context says so**
  (**D-185**). A model given only June will otherwise answer "pricing was
  never discussed" when the truth is "not in June". The entry numbers do not
  change — `ENTRY_SEQUENCE_SQL` counts the whole deal — so a scoped answer
  still cites what is on screen.
- **A sentence becomes a filter proposal** (**D-186**), `POST /api/v2/ai/filter`
  on its own router because a filter is over the board rather than one deal.
  No deal content is sent. `app/ai_filters.py` validates the model's JSON
  against the vocabulary the board actually has and *names* what it dropped,
  which is what makes §14's "a query the user can inspect" true rather than
  said. Applying is the reader pressing a button, which writes the same URL
  parameters the filter bar writes. The board gained `minValue`/`maxValue`
  here, because §14's own example proposes a bound nothing could have
  applied.

**Latency is configuration, and it is sized by measurement** (**D-168**).
A reasoning model has a floor of tens of seconds before it has thought
about anything — `minimal` effort spends zero reasoning tokens and still
takes ~29s — so `openai_timeout_seconds` shipped at 20.0 and *no call
could ever have succeeded* on the configured `gpt-5-nano`: three attempts,
61s, 502. It is 90.0s now with `max_retries: 1`, clearing the measured
40.1s worst case (the 41-entry deal) with headroom, and retrying only what
a retry helps — a transient 429 or 5xx, not a timeout, which only
multiplies a wait the reader is already sitting through.
`openai_reasoning_effort` defaults to `low`, which costs a few hundred
reasoning tokens where the default effort costs 2176-4480 and answers at
least as fully. Empty means *send no `reasoning` parameter*, which is what
a non-reasoning `OPENAI_MODEL` needs — the Responses API rejects the
parameter outright for those, so the call site carries the SDK's `omit`
sentinel rather than a `**kwargs` spread (the parameter is typed; a spread
of `dict[str, object]` matches no overload).

Two things about testing this, both learned from the defect above. Every
pre-existing AI test stubs the SDK, so all 19 passed while the feature was
non-functional — a default below a latency floor is invisible to a test
that never makes a real call, which is why
`test_the_ai_timeout_clears_a_reasoning_models_floor_latency` asserts a
bound on the default itself. And the reasoning guards assert on the
**serialized request body** through an `httpx.MockTransport`, not on the
kwargs passed to the SDK: the SDK strips `omit` before sending, so a
kwargs-level test cannot tell "parameter omitted" from "parameter sent as
a sentinel" — the distinction this fix turns on.

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

**Six routes inside one shell** (milestone R.1). `app/AppShell.tsx` is the
layout route every screen sits in: a collapsible rail of destinations down the
left (`lib/nav.ts`), the application bar above whatever the route renders, and
the session resolved **once** — so a signed-out reader meets the sign-in panel
on all of them rather than five different answers (**D-191**). Before it, four
of the five screens hand-rolled their own `header.topbar` with no navigation in
it, and Reports had no way to reach Automations.

`/` is `app/DashboardPage.tsx`, `/opportunities/:opportunityId` is
`app/OpportunityPanel.tsx`, and `/search`, `/tasks`, `/reports` and
`/automations` are their own pages. Anything else redirects to `/`.

**A deal is a page, not a panel under the board** (**D-188**, decision 1A of
the layout pass). It used to be a child route of the dashboard, which appended
it *below* a full screen of board: the first pixel of the thing the reader had
just clicked sat at y 888 on a 900px screen, under two filter bars and two
saved-view strips acting on a list they were no longer looking at. Two
consequences to keep:

- **The board's view state travels with the link.** `lib/viewState.ts`'s
  `opportunityHref` carries every `opportunities.*` parameter into the deal's
  URL and `boardHref` hands them back, so the filters, the sort, the chosen
  view and the month survive the round trip. Without it, opening a deal
  silently cleared the list the reader had built.
- **`OpportunityPanel` re-keys its body on the id**, so filters and a
  half-finished entry edit cannot leak from one opportunity into the next.

Milestone 2.1 decomposed the former `app/Home.tsx` — 1,863 lines, 28 `useState`
hooks, every read copied into component state — into these components, none
over 200 lines and each holding only its own form state: `AuthPanel`, `TopBar`,
`NotificationMenu`, `OpportunityForm`, `StageBoard`, `SharingPanel`,
`TimelineFilterBar`, `TimelineEntryForm`, `TimelineEntryList`, `NoteBlock`,
`AiSidebar`.

### The six aggregations

Milestone 6.2 is `docs/FEATURES.md` §10: what a sales manager needs to know
"without opening twenty opportunities one at a time". `app/dashboard.py` holds
all six, `routes_dashboard.py` answers them in one request, and
`app/ReportsPage.tsx` draws them at **`/reports`** — not `/dashboard`, because
this project's code has always called the board at `/` the dashboard and
reusing the word would make every reference ambiguous.

- **Computed live, and that is a constraint rather than a default.** §10 rules
  out rollup tables, materialized views and a warehouse by name. Six indexed
  aggregate queries is the whole implementation.
- **Permissions are inside each query**, as in search — this is the second
  read in the app that spans opportunities, so there is no role to resolve
  first and two managers legitimately get different numbers.
- **The 300 ms budget is asserted, and it is the only acceptance criterion in
  this project that is a number** (`test_each_aggregate_answers_inside_the_
  budget`, which builds §10's own 800,000-row corpus). It immediately found
  three of the six over budget (**D-172**): the stalled list became one
  grouped pass rather than a correlated `MAX` per deal, three covering indexes
  make that pass index-only, a partial index on `type = 'stage_change'` turned
  time-in-stage into a seek, and the activity union materializes the
  accessible set once. Worst case 196 ms.
- **Two queries name their index** (`INDEXED BY`), which is normally a smell.
  SQLite chose wrong in both directions depending on whether `ANALYZE` had
  run, and nothing here runs it — so the plan that matters is the one without
  statistics, and a directive that goes stale fails loudly rather than
  silently getting slow. Used only where measurement showed the planner
  choosing wrong. **§10's own suggested index order is inverted** for the same
  reason: it asks for `(created_by, created_at)` and the query filters on the
  date, so revision `0017_activity_indexes` creates
  `(created_at, created_by)`.
- **A metric that cannot be computed says so.** Average time in stage is only
  correct back to the first recorded stage change, so the response carries
  `earliest_change` and an unmeasured stage answers `null` — §10 requires that
  be "labelled as such rather than silently shown as zero", and the screen and
  an e2e test both hold it to that. A win rate with nothing closed is `null`
  rather than 0%, which is a different claim.
- **`currency` is on the response, beyond §10.** Four of the six sum `value`
  and a deal carries its own currency, so a mixed-currency deployment would
  get a number rather than an amount. It names the currency when there is one
  and is `null` when there is not; the screen then says "mixed currencies"
  instead of stamping a symbol on it.
- **Not paginated**, unlike every other collection read: six fixed summaries
  rather than a list somebody walks. The two that could grow take explicit
  caps, because a cursor over an aggregate is a cursor over something that
  changes under it.
- **The bars are CSS**, not a charting library (D-073's rule: a primitive
  arrives with the milestone that has a caller for it). Each report is a named
  landmark via `aria-labelledby` — a `<section>` is only a `region` once it
  has an accessible name, and six unnamed ones are six things a screen-reader
  user cannot tell apart.

### Automations

Milestone 6.3 is `docs/FEATURES.md` §11: *"if nothing has happened in two
weeks, remind me" is a rule every rep keeps in their head and forgets under
pressure.* Revision `0018_automation_rules` adds `automation_rules` and
`automation_runs`; `app/automations.py` is the evaluator,
`routes_automations.py` the API, `app/AutomationsPage.tsx` the screen at
**`/automations`**.

- **A constrained builder, not a workflow engine**, and the constraint is in
  the schema: one trigger column, one flat ANDed condition list, one action.
  A rule that branches cannot be stored. Parameters are JSON
  (`trigger_config`, `action_config`) validated on write against the two
  tables in `schemas.py` (`TRIGGER_*_KEYS`, `ACTION_*_KEYS`) — a key the
  chosen kind does not take is a 422 rather than a silently ignored field,
  because the stored rule has to mean what was on screen.
- **A rule acts with its creator's authority** (**D-173**). Evaluated only
  over the deals its creator can read, attributed to the creator, and the
  role the action needs re-checked **per deal at run time** —
  `ACTION_REQUIRES` is that table, and `change_stage` is owner-only there for
  the same reason `PATCH /opportunities/{id}` is. A rule naming an action its
  creator may not perform on a matched deal records `skipped` with the
  reason. That is what makes creation open to any authenticated caller (D-171's
  rule): a rule grants its author nothing they did not already have.
  **Editing, archiving and running one is the creator's alone**, which is the
  one place this departs from custom fields — a rule performs writes recorded
  under its creator's name. Listing is open, so "which automations run here,
  and whose" is answerable.
- **One hop, structurally** (**D-174**). Nothing in `automations.py` calls
  `fire_event` or `run_rule`, the evaluator is invoked only from the route
  handlers that perform *human* writes, and every write a rule makes is
  `system_generated`, which no trigger reads. The chain cannot exist, so
  there is no loop detection — which is what §11 asks for.
  `test_invariant_a_rule_cannot_trigger_a_rule` is a source scan, like
  `test_soft_delete.py`'s.
- **All five triggers, one evaluator** (**D-175**). The three event-driven
  ones (`stage_changed`, `entry_created`, `field_changed`) fire from
  `fire_event_after_commit` below the route's commit, where `publish_*` sits
  and for the same ordering reason; the two time-driven ones (`no_activity`,
  `close_date_approaching`) are evaluated by `run_rule`, which the manual
  run/preview route calls now and milestone 6.5's scheduler will call on a
  timer. `field_changed` is woken by the fields a `PATCH` actually moved,
  custom values compared against their previous value — a JSON column is
  written whole, so a form resending a value unchanged would otherwise look
  like a change.
- **Dry run is the same code path with the write turned off**, and `dry_run`
  **defaults to true** — the one default in this API that decides whether
  anything is written.
- **Every applied action leaves a system entry naming the rule**, which is
  §11's requirement and `AGENTS.md` standard 5's. There is **no `automation`
  entry type** (**D-176**): `type` is CHECK-constrained, so a new value is a
  full table rebuild, and `system_generated = 1` plus the rule's name in the
  body is what §11 actually asks for. Since 6.3a the entry also travels with
  `TimelineEntryPublic.automation_rule_id` — read per page from
  `automation_rule_ids_by_entry_id`, indexed by revision `0019` — because the
  card needs to tell an automation's entry from a person's. `change_stage` writes the ordinary
  `stage_change` entry so 6.2's time-in-stage reads one type for one event,
  and an `add_entry` action may **not** name `stage_change` — a rule writing
  that type would feed the dashboard a move that never happened.
- **An automated write records a version, like every other write**
  (**D-178**). `AGENTS.md` invariant 8 says every user-editable field keeps
  its previous value attributed to who changed it, and that "quietly
  rewriting one must be [traceable] too" — which is precisely what an
  unattended writer does. So `change_stage` records an
  `opportunity_versions` row and a rule-created task gets version 1 at
  creation, both attributed to the rule's creator, and the owner can restore
  what a rule replaced. It does not double up in the activity feed:
  `activity.py` already drops an opportunity version whose only changed field
  is the stage. `_task_row` reads `routes_tasks.TASK_ROWS_SQL` rather than its
  own query, because `assignee_ids` has to be the canonical string
  `version_is_current` compares as text (4.6).
- **An entry a rule wrote can be deleted; one a person caused cannot**
  (**D-181**, the human's request at the 6.3 review). It is the single
  exception to "a system entry cannot be deleted", and it needs neither a new
  permission rule nor a new column: `require_delete_permission` is
  author-or-owner (D-005) and an automated entry's `created_by` is the rule's
  creator, so the existing check already means "the deal's owner, or whoever
  wrote the rule"; and `automation_runs.entry_id` is the predicate for "did a
  rule write this". **Editing one is still refused** — removing a mistake is
  not rewriting what the record says. The delete is soft, audited and
  undoable, and it does **not** undo the change: a stage a rule moved goes
  back through the version history (D-178).
- **The run log records matches, not evaluations** (**D-177**): applied,
  skipped-with-a-reason, failed; dry runs too, with the outcome they would
  have had; and nothing for a deal the conditions filtered out. The skip is
  the half that matters — a rule that matched and declined leaves no trace
  anywhere else.
- **A rule with no live definition behind a condition stops matching.**
  Conditions read custom values through `visible_values`, so archiving a
  field disarms the rules that read it rather than leaving them acting on a
  value nobody can see (ADR 0006's never-trust-the-column-on-read).
- **The frontend draws a rule as a sentence** (`lib/domain.ts`'s
  `automationSentence`), in the list and live above the controls that build
  it: a column of selects says what the options are, not what was built,
  which is §11's own objection to a workflow engine. `automationTriggers` and
  `automationActions` declare what each kind is called and which parameters
  it takes, mirroring the server's two tables, so the form cannot offer what
  the API refuses. An archived rule is reachable behind a toggle, because its
  run log is the reason the row is kept and there is no DELETE route.

### Custom fields

Milestone 6.1 is ADR 0006 and `docs/FEATURES.md` §3: the two or three things
a sales team tracks that nobody anticipated, which otherwise live in body
text where nothing can filter on them. Revision `0016_custom_fields` adds
`custom_field_definitions` and a `custom_values` JSON column on both
`opportunities` and `timeline_entries`.

- **Who may define one is the widest write surface in the app** (**D-171**).
  §3 says "admin-defined" and there is no admin role here, so the rule is
  *any authenticated caller* — not the saved views' creator-only rule, because
  a field is shared by construction rather than personal (a typo in a label
  everyone reads should not be fixable only by whoever typed it). The creator
  is recorded, so narrowing this later is a route change rather than a
  migration, and every actor row in `test_authorization_matrix.py` pins the
  rule so a change to it cannot be silent.
- **Validated on write, never trusted on read** — the ADR's two rules, and
  both are load bearing. `custom_fields.validated_values` checks a submitted
  set against the live definitions; `visible_values` drops any key with no
  live definition, which is what lets a field be **archived without rewriting
  a single row** and restored with its values intact. That property is why
  there is no DELETE route and why a type change is archive-and-recreate.
- **A 422 that names the field.** `custom_values_or_422` raises a
  `RequestValidationError` rather than an `HTTPException`, so `errors.py`'s
  existing handler produces `fields: {"custom_values.region": ...}` — the half
  of a 422 a form can act on (`docs/REVIEW.md` M4). It is the one validation
  that runs inside a route and still answers like a schema failure, because a
  value is only wrong relative to a definition and Pydantic cannot see one.
- **A value set is written whole.** `null` and an absent key both mean "leave
  what is there", because a JSON column has no partial update and a quiet
  default is what stops every `PATCH` of a name clearing a deal's fields. An
  empty object is how a value is cleared. `required` is enforced when a set is
  submitted rather than on every write, so making a field required does not
  break screens that post without it.
- **Definitions are read once per request and passed down**, not looked up per
  row: `opportunity_from_row` and `entry_from_row` take a `definitions`
  argument, the shape `attachments_by_entry_id` already uses for a page.
- **The frontend reads one definition list per entity type**
  (`useCustomFields`), and three screens draw from it — the column picker, the
  filter bar and both forms, through `app/CustomFieldInputs.tsx`. A custom
  column is keyed `custom:<key>` so a field called `stage` is still not the
  stage; it is **read-only and not sortable**, because a value's editor
  depends on its type and `sortFields` is a fixed list. `lib/domain.ts` holds
  the pure half — `customFilters`, `matchesCustomFilters`, `customFieldText`,
  `columnsFromState` — and every one of them ignores a key with no live
  definition, so archiving a field quietly removes it from a saved view and a
  bookmarked URL rather than emptying the screen.
- **No expression index yet.** The ADR asks for one where a field is filtered
  often; at 400 opportunities none is needed, and one per field would be the
  user-triggered DDL the ADR rejected. That choice belongs with the field that
  earns it.

### Four views over one list

Milestones 2.7 and 2.8 gave the dashboard four renderers over one dataset, and
the shape of that is worth knowing before adding a fifth:

- **The filter controls are a disclosure** (R.1, **D-190**): a trigger, and
  what is in force as a removable chip each (`appliedOpportunityFilters` in
  `lib/domain.ts`). Eight permanently open controls were 77px at 1440 and
  320px at 420, and grew by a row for every custom field anybody defined. The
  open state belongs to `DashboardPage` rather than to the bar, for two
  reasons: `/` has to open it before it can put the cursor in the keyword box,
  and a filter arriving from a saved view or the AI's proposal opens it while
  the bar's own writes — a chip removed, Apply, Clear — deliberately do not.
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
  label (**D-090**). Its cells are edited in place from 2.11 (**D-087**
  deferred that here).
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
  `useEditOpportunity`: a partial `PATCH {stage}`, optimistic, rolled
  back with a toast, invalidating the timeline because the server writes the
  `stage_change` system entry. Since 2.11 that hook is every partial write to
  an opportunity, not only the stage one. The drag itself is the browser's own HTML5
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
- **The sidebar reads one step down** (3.8): `.sidebar-column` sets a smaller
  font size and 34px controls for everything inside it — the AI panel, the
  opportunity's own fields, the sharing panel. Scoped to the column rather than
  made a variant of each component, the same reasoning `lib/density.ts` uses
  for row height (D-075, D-089): what changes is where these things are, not
  what they are. 34px is the filter bar's own control height and clears WCAG
  2.2 AA's 24px target minimum, so this is a scale change and not an
  accessibility one.
- **A field is edited where it is read** (2.11): the account, value and close
  date cells, and the same fields on the opportunity's own heading, are
  `app/InlineEdit.tsx` over one declaration in `lib/domain.ts`
  (`editableOpportunityFields`). See "Editing where content is read" below.
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
`keys.allActivity`, since both write an audit row and neither knows which
opportunity the row belongs to — that prefix replaced `keys.allAuditLogs`
when 3.1c made the activity log the only reader of those rows.

**Server state does not live in components.** `lib/queries.ts` declares every
read and write the app makes against the query cache: the query keys, every
read, and each mutation with what it invalidates. A view calls a hook; a write
invalidates a key. Do not add a bare `apiRequest` call to a component — that is
the pattern ADR 0005 calls blocker B1, and 2.1 is what removed the last of it.
Most of the reads go through `fetchAll`, which walks `next_cursor` to the last
page: the API paginates every collection, and the board's cursor, its bulk
selection and the calendar's month are all derived from the whole filtered
list rather than from a window of it (**D-093**). The exceptions ask for one
page with an explicit limit, because an inbox and a saved-view menu are read
from the top. `useAuditLog` was a read here until 3.1c, which left the audit
rows to the activity log rather than to a panel of their own (**D-121**).
`useMembers` (3.2) is the composer's `@` list, invalidated by every sharing
write and by a bulk `assign_owner`.
Two things in there are worth knowing before changing them: the AI transcript is
cache state under `["ai-conversation", id]` because it has to outlive the route
(D-055), and the cache is dropped on *sign-in*, not sign-out, because observers
are still mounted for one render after logout and removing their queries makes
them refetch (D-056).

The units worth testing directly, each in its own module:

- `lib/api.ts` — `apiRequest<T>()`, the only fetch wrapper
  (`credentials: "include"`, echoes the CSRF cookie on unsafe methods, throws
  `ApiError` on non-2xx carrying the envelope's `error.message`, its
  `error.code` and — since 6.3a (**D-180**) — its `error.fields`, the
  per-field reasons a 422 names. `isConflict` is the first caller to branch on
  the code, for the note edit guard; `AutomationRuleForm` is the first to read
  `fields`, and until it did, every refused form in this app said only "The
  request could not be validated" however precisely the API had answered).
- `lib/query.ts` — `createQueryClient()`, the single TanStack Query
  configuration (no retries: `apiRequest` throws on 401 and 422 too).
- `lib/snippet.ts` — turns a search snippet's match offsets into runs to
  highlight. The API sends text and offsets, never markup.
- `lib/time.ts` — the UTC/`datetime-local` conversions at both boundaries.
- `lib/permissions.ts` — `canManageOpportunity` / `canWriteTimeline` /
  `canChangeItem`, the client mirror of `backend/app/permissions.py`. They decide
  which buttons are offered, never who is allowed to do what.
- `lib/notifications.ts` — the sentence shown for each notification type.
- `lib/aiStream.ts` — reading a streamed answer: `fetch` plus a reader, SSE
  framing, and the two event types the reply has (6.4, D-187). Not
  `apiRequest`, which reads a body whole.
- `lib/formErrors.ts` — `invalidFields`, what the *browser* refused, keyed by
  each control's `name` and therefore by the API's own field path (6.5a,
  **D-184**). A form that leaves validation to the browser gets a submit
  cancelled before its code runs and a tooltip that vanishes, which is how a
  number field holding `e` came to be silent; `AutomationRuleForm` is the
  first caller and sets `noValidate` so it can ask the question itself. The
  rest of the forms can adopt it.
- `lib/jobs.ts` — the one line the automations screen says about the
  scheduler: when the rules were last checked, or that nothing has checked
  them, or that a check started and did not finish (6.5, D-183).
- `lib/activity.ts` — the same job for the activity log's three kinds of
  event, and `versionFieldLabel`, which reads a changed column's name off the
  history screen's own declaration rather than a second list.
- `lib/domain.ts` — the fixed stage list, the entry types, the short names for
  the generated schemas, and the two view states (`TimelineFilters`,
  `OpportunityViewState`) with `applyOpportunityView`, which filters and sorts
  the already-fetched opportunity list in the client. One definition, because
  several views read them. Also what the four opportunity views share:
  `viewOrder` (reading order), `adjacentStage` (`[` and `]`, which stop at the
  ends of the fixed list), `formatMoney`, the `sortFields` and
  `opportunityColumns` lists with `columnsFromState`/`opportunityCell`, and the
  calendar's date arithmetic (`resolveMonth`, `shiftMonth`, `calendarWeeks`,
  `monthOrder`). Also `editableOpportunityFields` and `editableField`, which
  say which fields are edited in place and how (2.11).
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
- `lib/markdown.ts` — the node set the composer and the renderer share, and
  Markdown to and from an editor document (3.1). See "The composer".
- `lib/suggestions.ts` — what `@`, `/` and `#` offer, and what choosing one
  inserts: text, a link, or a command over the block (3.2). Holds no editor
  call, so the whole list is tested without a DOM.
- `lib/liveUpdates.ts` — which reads one pushed event makes stale, and the
  hook that opens the stream for as long as a timeline is on screen (3.4).
  See "Live updates". `app/test-live-updates.ts` is the fake `EventSource`
  the component tests drive it with; jsdom implements none.
- `app/InlineEdit.tsx` — `useInlineEditor` and `InlineEdit`, the two shapes
  of "edit this where it is read" (2.11). See "Editing where content is read".
- `app/RichTextEditor.tsx` — `RichTextEditor` and `Composer`, the two shapes
  of "write content here" (3.1). See "The composer".
- `app/Suggestions.tsx` — the popup all three triggers share, and the context
  that tells it who is on this deal (3.2). See "The three typed triggers".
- `app/VersionChanges.tsx` — what one edit changed, and the control that puts
  the earlier version back (3.1c). Rendered inside an activity row rather than
  in a dialog of its own; see "Edit history" and "One activity log".
- `app/CommentThread.tsx` — one discussion on a note: its replies, its Reply
  control and its resolved state (3.3). See "Threaded comments".
- `app/AttachmentList.tsx` — one entry's files, the collapsed picker that adds
  one, and the link that downloads one (4.3). See "Attachments". `formatBytes`
  in `lib/domain.ts` is the size as a person reads it, for the same reason
  `formatMoney` is there.
- `app/Toasts.tsx` — the toast surface and `useUndoableDelete`, the one
  definition of "delete it, and say so with a way back" (milestone 2.4b). The
  region is a `role="status"` live region, never focused, so a reader keeps
  their place; the toast lasts `TOAST_DURATION_MS` (10 s, the window
  `docs/UX.md` names). Both legs go through `mutateAsync`, because the control
  that started the delete has usually unmounted by the time it resolves —
  deleting a note unmounts the note — and TanStack Query drops
  `mutate(vars, { onSuccess })` once the observer has no listeners.
- `app/MarkdownText.tsx` — entry, note and comment bodies (all three since
  3.1), rendered through `rehype-sanitize` with an explicit
  `http`/`https`/`mailto` protocol allowlist, which is `lib/markdown.ts`'s
  `linkProtocols`. Keep that allowlist if you touch the Markdown pipeline. A
  href starting with `/` is rendered as a router `Link` (3.2, D-124) —
  everything else opens in a new tab. Its
  one control is a checklist's box, which `remark-gfm` emits unnamed — named
  here, because an unlabelled form control fails axe for the whole screen.
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
  `isTypingTarget`, which reads both `isContentEditable` and the attribute,
  because jsdom implements the first as `undefined` and the composer is a
  contenteditable `div` (**D-112**) — while `Ctrl K` and `Esc` still work there, which is what
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

### Keyboard, focus and the accessibility bar

Milestone R.2. `AGENTS.md`'s Quality Bar is **WCAG 2.2 AA** and **D-002**
ruled that over the brief's 2.1 — but `auditPage`'s tag list asked axe for 2.1
from Phase F until R.2, so every "axe clean" claim up to R.1 was a 2.1 claim
(**D-197**). The tags are 2.2 now. Five things follow:

- **axe checks one of 2.2's additions and none of the other three.**
  `target-size` (2.5.8) is machine-checkable and passed on the first run,
  because R.1 reduced seven control heights to one 34px token. 2.4.11, 2.5.7
  and 3.3.8 are not, and are in `e2e/30-focus-and-keyboard.spec.ts` and
  `app/AuthPanel.tsx` instead. 3.3.7 and 3.2.6 do not apply (no multi-step
  form, and the one help mechanism is already global).
- **Nothing that has focus may be entirely hidden** (2.4.11, **D-198**).
  `Shift+Tab` up a timeline scrolls a control to the top edge of the
  scrollport, which on a deal is under 190px of application bar and record
  band: 15 controls, measured on the shipped R.1 build. The fix is
  `scroll-padding-top` on the **scrolling element**, not `scroll-margin-top`
  on the controls — the browser scrolls nothing for an element it already
  considers in view, and a control under a sticky band is in view as far as
  the viewport rectangle is concerned. The two stacks are `--sticky-bar` and
  `--sticky-deal`, the same numbers the bands themselves stick at, and which
  one is in force is `data-sticky` on `<html>` from `lib/nav.ts`'s
  `stickyStack` — a document-level fact as a root attribute, the shape
  `lib/theme.ts` and `lib/density.ts` use.
- **A skip link, and it moves the keyboard** (2.4.1, **D-199**). The rail
  repeats six destinations above every screen. `#main-content` carries
  `tabIndex={-1}`, without which the anchor scrolls the page and leaves focus
  in the rail — the usual way this ships broken.
- **A navigation moves focus into the screen it opened.** Clicking a rail link
  left focus on the rail while everything else changed, so the next Tab
  continued through navigation. `useFocusOnNavigate` focuses the content
  region, with `preventScroll` (two other things already decide where the
  screen sits) and never on the first render, because a page load is not a
  navigation.
- **Anything that measures a box or a colour waits for transitions to settle.**
  `settleTransitions` in `e2e/helpers.ts`: the first 2.2 run reported 2.43:1 on
  the deal page's Ask button, which was axe sampling a 120ms colour transition
  60ms in. Transitions only — the skeleton shimmer and the AI cursor run
  forever, and `finished` on an infinite animation never resolves.

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
  frontend change, not a migration — which is what makes a *curated* view
  possible without a membership table: "add to view" (3.0a) writes the
  selection into an `ids` filter (**D-106**), read by `lib/domain.ts`'s
  `pinnedIds` like every other filter, so it serialises to
  `?opportunities.ids=3,7` and is shareable and reloadable for free. It is a
  filter and not an ordering, and the size cap is what bounds how many deals
  one view can pin — the route answers 400 rather than truncating.
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
- **A control holds its label, and geometry is tested** (milestone 3.8,
  **D-138**). The base button rule carried `min-width: 0` with
  `overflow-wrap: anywhere` from the MVP, so any flex row short of room broke a
  button's label to one character per line — `Share` at 30x106, `Delete` at
  43x124, `New opportunity` at 42x227. It was reported at three gate reviews
  and each report was read as a different local layout bug. The rule now says
  `white-space: nowrap` and `flex-shrink: 0`; the rows that used to squeeze a
  control (`.inline-actions` and the four heading rows beside it,
  `.user-block`, `.page-actions`, `.calendar-toolbar`) wrap instead, and the
  text half of each carries the `min-width: 0` that lets it yield. The trade is
  deliberate: a label that cannot fit now overflows, which is visible, rather
  than collapsing, which reads as broken — and **`e2e/23-responsive.spec.ts` is
  what makes the trade safe.** It walks six screens at eight widths from 1440
  to 420 and fails on any control taller than wide or any page whose
  `body.scrollWidth` exceeds the viewport, collecting every violation rather
  than stopping at the first. Nothing in this project measured a rendered box
  before it, which is how a defect this visible survived three phases and two
  gates.
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

`tools/scale.py` is the one corpus builder at `AGENTS.md`'s confirmed scale —
400 deals, 80,000 entries, ~805,000 rows — shared by `make seed-scale` and
`tests/test_performance.py` (R.7, **D-208**), so what a person loads is what
the budgets were measured against. It is composable: every id it generates is
relative to `MAX(id)`, which is what lets it run on top of the demo seed
without a generated note attaching itself to one of the five deals somebody is
about to read.

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
runs on every screen, in both themes, against **WCAG 2.2 AA** — see "Keyboard,
focus and the accessibility bar" below for what that does and does not check.
`DEFERRED_AXE_RULES` in `e2e/helpers.ts` is a ratchet, not an allowlist: it has
been empty since milestone 2.5, any rule fails immediately, and a test asserts
that anything on the list still fails — so nothing can be added to it and left
there once the problem is gone.

Three rules the suite has already been bitten by:
- Assertions must not depend on the wall clock. The auto-generated "Opportunity
  created" entry is stamped with the current time, so anchor date windows to `now`
  (see the `days_ago` helper in `test_timeline.py`) rather than hardcoding dates.
- A guard test should be confirmed to fail against the unfixed code before it is
  trusted.
- In Playwright, do not filter a locator by text you are about to change — the
  locator stops matching mid-test. Address the element by position instead.

**`npm audit` is a ratchet, not a wall** (R.6, **D-207**).
`scripts/audit-gate.mjs` is what `make check` runs: a high or critical
advisory with no entry in its allowlist fails, **and** an allowlisted advisory
that no longer appears also fails, so an entry cannot outlive the problem it
documents — the same bargain `DEFERRED_AXE_RULES` makes. The single entry
today is GHSA-vfj7-8cjw-p6xm in `braces`, which has no fix anywhere (the
advisory covers `<= 3.0.3` and that is the newest release there has ever
been) and is reachable only at lint time, over this repository's own
configuration: `output: "export"` means no `node_modules` ships. Nothing may
be added there without the reason it is safe *in this deployment*.

`.github/workflows/ci.yml` runs `make check` plus the Docker-only steps the
sandbox cannot, and uploads coverage from both suites and Playwright's report
on `always()`. `PYTEST_ADDOPTS` supplies `--cov-report=xml` in CI only, so a
local run still leaves no files behind.

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
