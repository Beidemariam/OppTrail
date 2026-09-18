# OppTrail v2 — Architecture

Companion to the ADRs in `docs/adr/`. This document states the shape of the system
and the cross-cutting standards; the ADRs carry the reasoning for each choice.

## The decision that shapes everything else

Confirmed target scale: **20 users, 20 opportunities each (400 total), ~200 entries
per opportunity, 2-3 concurrent**. That is **~800,000 rows and a ~136 MB database**
— seeded and benchmarked, not estimated.

This is small, and saying so plainly is the most useful thing this document does.
It means the infrastructure half of a "ClickUp-class" brief — Postgres, a message
broker, a job queue, object storage, a multi-tenant hierarchy — is not merely
premature but actively harmful here: it would consume the entire v2 budget building
scaffolding for load that will not arrive, while the actual gap (interaction
quality) went unaddressed.

The v2 goal is therefore restated as: **ClickUp-class interaction quality on
deliberately boring infrastructure.**

## Target architecture

```
                     one Docker container
  ┌──────────────────────────────────────────────────────────┐
  │  FastAPI (single process, single instance)               │
  │                                                          │
  │   /            static React bundle (built by Next.js)    │
  │   /api/*       JSON API, session cookie auth             │
  │   /api/.../events   SSE invalidation stream    ADR 0003  │
  │                                                          │
  │   APScheduler  digests, reminders, IMAP poll,  ADR 0004  │
  │                backups                                   │
  │   OpenAI       read-only agent, no tools       ADR 0012  │
  └───────────────┬──────────────────────────────────────────┘
                  │
        /data volume
          app.db          SQLite + WAL + FTS5    ADR 0001, 0007
          attachments/    content-addressed      ADR 0008
          backups/        VACUUM INTO snapshots  ADR 0011
```

Unchanged from v1: one image, one process, one volume, one origin. No CORS, no
reverse proxy, no service discovery, no broker.

### Frontend

React SPA, routed client-side, built by Next.js in static-export mode. Next is
**explicitly a build tool** — no SSR, no server components, no API routes
(ADR 0005). Deep links work because FastAPI serves `index.html` for any unmatched
path (`main.py:56-64`).

- **React Router** — URL is the source of truth for opportunity, view, and filters.
- **TanStack Query** — the only server-state cache; SSE events invalidate keys.
- `app/[[...slug]]/page.tsx` is the single exported HTML file; `app/AppRoot.tsx`
  holds the router and the query client, and `/search` is the second route that
  justified introducing both (milestone 1.5). `app/Home.tsx` — the former
  `page.tsx` — decomposes into routed views and feature components in milestone
  2.1. Local state lives in the component that owns it.

### Backend

Keep the current module shape — it is sound. Additions:

- `deps.py` — the `OpportunityContext` dependency that makes authorization
  structural rather than conventional (ADR 0010).
- `search.py` — FTS5 index maintenance and query (ADR 0007).
- `email_inbound.py` / `email_outbound.py` — parsing behind a transport interface
  (ADR 0009).
- `jobs/` — scheduled tasks, framework-free so they stay directly testable.
- `attachments.py` — validation, content addressing, streamed download (ADR 0008).
- Alembic replaces `schema.sql` + `run_migrations()` (ADR 0002).

## Cross-cutting standards

### Authorization

One rule: **no endpoint touches an opportunity-scoped object without passing through
the `OpportunityContext` dependency.** Routes declare the level they need; nested
objects resolve to their opportunity inside the dependency. A route test enumerates
the app's routes and fails the build if any non-public route omits the guard
(ADR 0010).

### Timestamps

All timestamps are canonical fixed-width UTC (`%Y-%m-%dT%H:%M:%SZ`, `time_utils.py`).
Lexicographic comparison must remain equal to chronological comparison. No
`CURRENT_TIMESTAMP`, ever — every v2 migration and insert path inherits this.

### Untrusted input

Content arriving by email or attachment is **untrusted** and must be labelled with
its provenance everywhere it travels: in the database (`source`), in the UI, and in
the AI context (ADR 0012). This is new in v2 and is the single largest change to the
system's threat model.

### Error shapes

One envelope for every failure: `{"error": {"code", "message", "fields"?}}`.
Today hand-raised errors are `{"detail": "..."}` while Pydantic emits
`{"detail": [...]}`, and the client flattens every 422 to "Request failed" — so
users never learn which field was wrong. A single exception handler normalizes both.

### Pagination

Every collection endpoint is paginated from the start: `?limit&cursor`, returning
`{"items": [...], "next_cursor": null}`. Not for load — for the fact that adding it
later breaks every client. Ship it before the view layer is built (review blocker
B3).

### API versioning

New surface mounts under `/api/v2`. `/api/*` continues to serve v1 shapes until the
frontend has moved, then is removed. Pagination and the notification rework are both
breaking, so a version boundary is what makes them incremental.

## Testing strategy

The existing shape is right and should be extended, not replaced: integration tests
driving the real app through `TestClient` against a real SQLite file catch the bugs
that matter here, and they already cover the role matrix per resource.

| Layer | Tool | Scope | Target |
|-------|------|-------|--------|
| Unit | pytest | Pure logic: timestamps, email parsing, quote stripping, CSV escaping, custom-field validation | Fast, exhaustive on edge cases |
| Integration | pytest + `TestClient` | Every endpoint, every role, soft deletes, audit rows, pagination | **The bulk of the suite.** ≥90% of `backend/app` |
| Frontend unit | Vitest + Testing Library | Components with logic: filter builder, editor, views | ≥70% of `frontend/src` |
| E2E | Playwright | 5-8 critical flows only: sign in, create opportunity, log entry, share, search, export | Kept small deliberately |
| Security regression | pytest | Route-guard enumeration, path traversal, CSV injection, prompt injection, email spoofing | Every fixed vulnerability keeps its test |

Two rules the suite has already been bitten by, carried forward from `CLAUDE.md`:
assertions must not depend on the wall clock, and a guard test must be shown to fail
against the unfixed code before it is trusted.

## CI

There is none today — 39 tests that nothing runs (review blocker B4). GitHub Actions,
on every push and PR:

1. `uv run pytest --cov=app` with a coverage floor that fails the build.
2. `npm run typecheck`, `npm run lint`, `npm run test`.
3. `docker build`, then the backend suite **inside the image** — this is where
   WeasyPrint actually runs, and it already catches what the host cannot.
4. Playwright smoke against the built container.
5. Alembic check: migrations apply cleanly to an empty database *and* to a restored
   snapshot of the previous release's schema.

Step 5 is the one that protects the existing `data/app.db` from a bad migration, and
it is the reason ADR 0002 is a blocker rather than a nicety.

## Observability

Currently zero (review H3). Minimum viable, no vendor:

- **Structured JSON logs to stdout** with a request ID, user ID, route, status and
  duration. `routes_ai.py:43`'s bare `except Exception` must log the cause — it
  currently discards it, in direct contradiction of `AGENTS.md` standard 4.
- **Audit log stays separate.** It is a product feature for owners, not operations
  telemetry; do not conflate them.
- **`/api/health` reports substance**: schema version, database writability, last
  successful backup, IMAP poll status.
- **Job outcomes recorded** in the `outbox`/job table — a silently dead scheduler is
  the most likely v2 production failure.
- **Inbound email ingestion log**, including rejections. Silent drops are
  unacceptable when a colleague believes they filed a note (ADR 0009).

## Performance budgets

Concrete numbers, measured in CI against a seeded database at 2x target scale
(40 opportunities, 400 entries each):

Measured on a seeded database at exactly this scale (800,400 rows). Where a figure
was measured it is shown; the rest are targets.

| Operation | Budget (p95) | Measured today |
|-----------|--------------|----------------|
| Timeline load, 200 entries with notes and comments | **400 ms** API, **800 ms** to interactive | 1.4 ms (query) |
| Dashboard load, 400 opportunities with stalled state | **300 ms** API | 131 ms |
| View switch (timeline ↔ board ↔ table), data cached | **150 ms** | n/a (not built) |
| Keyword search across all opportunities | **300 ms** | 294 ms worst case (LIKE), 1-121 ms (FTS5) |
| Filter/sort change within a loaded view | **100 ms** | n/a |
| Entry create → visible to a second user via SSE | **2 s** | n/a |
| AI answer, complete | **15 s** (streamed, first token < 3 s) | n/a |
| PDF export, 200 entries | **5 s** | n/a |
| Initial JS bundle | **250 KB** gzipped | n/a |

Two things the measurements changed:

- **The dashboard N+1 passes.** 131 ms at 400 opportunities, well inside budget, and
  the obvious "single grouped query" rewrite measured **363 ms — three times
  slower**, because it unions all 800,000 rows instead of using the
  `opportunity_id` index. Do not apply that fix. If the dashboard ever needs to be
  faster, denormalize `last_activity_at` onto `opportunities`.
- **FTS5 is justified on worst-case latency and UX, not on raw speed.** `LIKE` is
  fast when matches are dense (it short-circuits on `LIMIT`) and slowest exactly
  when the user searches something specific: 294 ms for a term with no matches,
  against a 300 ms budget. FTS5 inverts that — 1 ms for a rare term — and adds
  ranking and snippets, which `LIKE` cannot provide at any speed.

Budgets are enforced in CI against a seeded database at this scale, so a regression
fails the build rather than being discovered in use.

## Accessibility target

**WCAG 2.2 AA**, treated as a build requirement rather than a later audit — the
current app has one `aria`/`role` attribute in 1,829 lines, so this starts from zero.

- Every interactive element reachable and operable by keyboard, with a visible focus
  ring. Dense, keyboard-first UI is a stated v2 goal, which makes this load-bearing
  rather than compliance theatre.
- Real dialogs with focus trap and restore, replacing `window.confirm`.
- Live regions for async results and toasts.
- 4.5:1 contrast for text. **Measured against the current palette, three in-use
  pairs already fail** and need corrected tints in the token set: accent teal as
  link text is 3.38:1 (`globals.css:89,808`), alert red as error text is 4.38:1
  (`:231,:246`), and white on the red notification badge is 4.38:1 (`:266`). Slate
  gray passes at 4.58:1, and dark-on-amber badges pass at 7.72:1 — the brand colours
  are fine as fills, and unsafe as text. `DESIGN-SYSTEM.md` carries the fix.
- Never colour alone to convey meaning: entry types and stage badges need shape or
  text too.
- `axe` assertions in Playwright runs, so regressions fail CI.
