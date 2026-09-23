# PLAN.md

## Overview
OppTrail lets a sales team log every event in the life of an opportunity as a
timestamped timeline entry, attach follow-up notes to any entry at any time, and
discuss those notes via comment threads. Opportunities can be shared with
colleagues as Viewer or Editor. An AI sidebar answers summarized questions about
an opportunity's history, and the full timeline can be exported to PDF or raw
data. See AGENTS.md for the full requirements and scope boundaries this plan
implements.

## Architecture
```
Browser
  -> NextJS (static export) served by FastAPI at /
  -> FastAPI backend (/api/*)
       -> SQLite (app.db)
       -> OpenAI (AI agent calls)
       -> WeasyPrint (PDF rendering, in-process)
  All packaged in one Docker container
```
No background workers or queues in MVP — every request is handled synchronously.
No websockets — the frontend polls the timeline endpoint on an interval while an
opportunity view is open, which is enough for a small shared team and keeps the
system simple per the coding standards.

## Data Model

**User**
- id, email (unique), password_hash, name, created_at

**Opportunity**
- id, name, account_name, value, currency, stage, owner_id (FK User),
  expected_close_date, created_at, updated_at, deleted_at (nullable)

**OpportunityShare**
- id, opportunity_id, user_id, role (`viewer` | `editor`), invited_by,
  created_at

**TimelineEntry**
- id, opportunity_id, type (`call` | `email` | `meeting` | `demo` | `proposal` |
  `contract` | `stage_change` | `other` | `site_visit` | `objection` |
  `competitor_intel` — the last three added by Phase 2 milestone 2.6), title,
  body, event_timestamp (editable — when the event happened), created_by,
  created_at (immutable — when it was logged), follow_up_date (nullable),
  deleted_at (nullable)

**Note**
- id, entry_id, body, created_by, created_at, updated_at, edited (bool),
  deleted_at (nullable)

**NoteVersion**
- id, note_id, version_number, body, edited_by, created_at
  (version 1 is captured when the note is created; each edit appends a new
  version row)

**OpportunityVersion** (Phase 2 milestone 2.10)
- id, opportunity_id, version_number, name, account_name, value, currency,
  stage, expected_close_date, edited_by, created_at

**TimelineEntryVersion** (Phase 2 milestone 2.10)
- id, entry_id, version_number, type, title, body, event_timestamp,
  follow_up_date, edited_by, created_at

  Both follow NoteVersion exactly: version 1 at creation, one appended row per
  edit holding the whole resulting state, never an update. `app/versioning.py`
  is the only writer. System-generated entries are never versioned — they
  cannot be edited.

**Comment**
- id, note_id, body, created_by, created_at, deleted_at (nullable)
  (comments are not editable after posting — see Open Questions)

**Notification**
- id, user_id, type (`mention` | `comment` | `share_added` | ...), payload
  (JSON), read (bool), created_at

**AuditLogEntry**
- id, opportunity_id, actor_id, action, detail (JSON), created_at

## API Surface

One surface, `/api/v2/*`. v1 (`/api/*`) served the MVP frontend and was
removed at the end of roadmap Phase 2, once the frontend had moved
(`docs/ROADMAP.md`'s breaking-changes table, milestone 2.9). Two rules hold
across all of it (`docs/ARCHITECTURE.md`, "Pagination" / "Error shapes"):

- Every collection read takes `?limit` (1-200, default 50) and `?cursor`, and
  answers `{"items": [...], "next_cursor": null}`.
- Every failure answers `{"error": {"code", "message", "fields"?}}`, with
  `fields` present on validation errors.

**Auth**
- `POST /api/v2/auth/signup`
- `POST /api/v2/auth/login`
- `POST /api/v2/auth/logout`
- `POST /api/v2/auth/password` — invalidates every session of that user
- `GET  /api/v2/auth/me`

**Opportunities**
- `GET    /api/v2/opportunities` — owned + shared, with stage/stalled info
- `GET    /api/v2/stages` — the fixed stage list, which v1 carried as a field
  on the opportunity list response and the envelope has no room for
- `POST   /api/v2/opportunities`
- `GET    /api/v2/opportunities/{id}`
- `PATCH  /api/v2/opportunities/{id}` — including stage changes (auto-logs a
  system TimelineEntry); appends an OpportunityVersion
- `GET    /api/v2/opportunities/{id}/versions` — owner only, edit history
- `DELETE /api/v2/opportunities/{id}` — owner only, soft delete
- `POST   /api/v2/opportunities/{id}/restore` — owner only, undoes the above
- `POST   /api/v2/opportunities/bulk` — one action over many ids, per-item
  results

**Sharing**
- `GET    /api/v2/opportunities/{id}/shares`
- `POST   /api/v2/opportunities/{id}/shares` — `{email, role}`
- `PATCH  /api/v2/opportunities/{id}/shares/{user_id}` — `{role}`
- `DELETE /api/v2/opportunities/{id}/shares/{user_id}`

**Timeline**
- `GET    /api/v2/opportunities/{id}/timeline` — supports
  `?q=&type=&from=&to=&author_id=&order=`
- `POST   /api/v2/opportunities/{id}/timeline`
- `PATCH  /api/v2/timeline/{entry_id}` — appends a TimelineEntryVersion
- `GET    /api/v2/timeline/{entry_id}/versions` — owner only, edit history
- `DELETE /api/v2/timeline/{entry_id}` — soft delete
- `POST   /api/v2/timeline/{entry_id}/restore`

**Notes**
- `POST   /api/v2/timeline/{entry_id}/notes`
- `PATCH  /api/v2/notes/{note_id}` — sets `edited = true` and appends a
  NoteVersion row
- `GET    /api/v2/notes/{note_id}/versions` — owner only since milestone 2.10
  (D-096), which gave the three histories one audience
- `DELETE /api/v2/notes/{note_id}` — soft delete
- `POST   /api/v2/notes/{note_id}/restore`

**Comments**
- `POST   /api/v2/notes/{note_id}/comments`
- `DELETE /api/v2/comments/{comment_id}` — soft delete, author or Owner only
- `POST   /api/v2/comments/{comment_id}/restore`

**AI Agent**
- `POST /api/v2/opportunities/{id}/ai/ask` — `{question}` ->
  `{answer, referenced_entry_ids}`

**Export**
- `GET /api/v2/opportunities/{id}/export/pdf`
- `GET /api/v2/opportunities/{id}/export/csv`
- `GET /api/v2/opportunities/{id}/export/json`

**Notifications**
- `GET   /api/v2/notifications` — full history, optional `?type=`
- `PATCH /api/v2/notifications/{id}/read`
- `POST  /api/v2/notifications/mark-all-read`

**Audit Log**
- `GET /api/v2/opportunities/{id}/audit-log` — owner only

**Search**
- `GET /api/v2/search` — ranked, snippeted matches in entries, notes and
  comments across every opportunity the caller can read, with the timeline's
  filters by the same names. An unbounded ranked result set is the shape the
  envelope exists to stop shipping, so search has always been
  paginated-only (ADR 0007).

**Saved views**
- `GET/POST /api/v2/saved-views`, `PATCH/DELETE /api/v2/saved-views/{id}` —
  creator-only write, creator-or-shared read

**Operations**
- `GET /api/health` — deliberately unversioned: an operations probe
  (ADR 0011), not part of the client surface.

All endpoints except `/api/v2/auth/*` and `/api/health` require a valid session and enforce the
Permissions Model from AGENTS.md server-side (not just hidden in the UI).

## Build Phases

**Phase 0 — Scaffolding**
- [x] Repo structure per AGENTS.md, Dockerfile, uv-managed backend, NextJS
      frontend skeleton
- [x] Start/stop scripts for Mac, PC, Linux
- [x] SQLite schema + migrations, `.env.example`
- Acceptance: container builds and serves an empty NextJS page through FastAPI

**Phase 1 — Auth, Opportunities, Dashboard**
- [x] Signup/login/logout, session cookie
- [x] Opportunity CRUD, dashboard list grouped by stage
- Acceptance: a user can sign up, create an opportunity, see it on the dashboard

**Phase 2 — Timeline Tree**
- [x] TimelineEntry CRUD, Note CRUD (addable to any entry at any time), Comment
      CRUD (addable to any note)
- [x] Permission checks enforced server-side for Viewer/Editor/Owner
- [x] Auto-logged system entries for stage changes and opportunity creation
- [x] Timeline search/filter (keyword, type, date range, author)
- Acceptance: a full entry -> note -> comment chain can be created, edited where
  allowed, searched/filtered, and a Viewer is blocked from writing

**Phase 3 — Sharing**
- [x] Invite by email, assign/change/remove role
- [x] Audit log entries for share/role changes
- [x] Auto-logged system timeline entries for share/role changes
- Acceptance: Owner shares with a second test user, who sees the opportunity
  with the correct permissions

**Phase 4 — AI Agent**
- [x] Backend assembles chronological timeline text, calls OpenAI
- [x] Sidebar chat UI, per-opportunity conversation
- Acceptance: asking "summarize this opportunity" returns a grounded answer
  referencing actual entries

**Phase 5 — Export**
- [x] PDF export via WeasyPrint (opportunity summary + full timeline)
- [x] CSV and JSON export of raw data
- Acceptance: exported PDF renders all entries/notes/comments in chronological
  order and matches the on-screen timeline

**Phase 6 — Notifications and Reminders**
- [x] @mentions -> Notification rows, notification bell UI
- [x] Stalled-opportunity flag using 14 days since latest non-deleted timeline
      activity
- [x] Follow-up reminder field on entries
- Acceptance: mentioning a colleague creates a notification they can see and
  dismiss

**Phase 7 — Polish**
- [x] Apply color scheme, responsive layout, empty states, loading states
- [x] Complete the phase gates in `docs/TEST_CRITERIA.md`
- Acceptance: full walkthrough (signup -> create opportunity -> log entries ->
  share -> AI question -> PDF export) works end to end in the Docker container

## Open Questions / Assumptions
Resolved with the following defaults so the build isn't blocked:
- **Deletes are soft deletes** everywhere (`deleted_at`), so nothing on a shared
  sales record silently disappears; a true purge is a DB-admin action outside
  the app
- **`event_timestamp` is editable, `created_at` is not** — lets someone log a
  call from yesterday while keeping an immutable record of when it was actually
  entered into the system
- **Notes are editable** (with an `edited` marker) since they're a living
  record; each note create/edit appends to `NoteVersion` for real version
  history; **comments are not editable** after posting, only deletable by their
  author or the Owner, to keep discussion threads simple and trustworthy
- **One flat user pool in MVP** — no organizations; any signed-in user can be
  invited to any opportunity by email, and must already have an account
- **Stalled means 14 days without activity** — activity is the latest
  non-deleted timeline entry, note, or comment timestamp on the opportunity
