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
  `contract` | `stage_change` | `other`), title, body, event_timestamp
  (editable — when the event happened), created_by, created_at (immutable —
  when it was logged), follow_up_date (nullable), deleted_at (nullable)

**Note**
- id, entry_id, body, created_by, created_at, updated_at, edited (bool),
  deleted_at (nullable)

**NoteVersion**
- id, note_id, version_number, body, edited_by, created_at
  (version 1 is captured when the note is created; each edit appends a new
  version row)

**Comment**
- id, note_id, body, created_by, created_at, deleted_at (nullable)
  (comments are not editable after posting — see Open Questions)

**Notification**
- id, user_id, type (`mention` | `comment` | `share_added` | ...), payload
  (JSON), read (bool), created_at

**AuditLogEntry**
- id, opportunity_id, actor_id, action, detail (JSON), created_at

## API Surface

**Auth**
- `POST /api/auth/signup`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET  /api/auth/me`

**Opportunities**
- `GET    /api/opportunities` — owned + shared, with stage/stalled info
- `POST   /api/opportunities`
- `GET    /api/opportunities/{id}`
- `PATCH  /api/opportunities/{id}` — including stage changes (auto-logs a
  system TimelineEntry)
- `DELETE /api/opportunities/{id}` — owner only, soft delete

**Sharing**
- `GET    /api/opportunities/{id}/shares`
- `POST   /api/opportunities/{id}/shares` — `{email, role}`
- `PATCH  /api/opportunities/{id}/shares/{user_id}` — `{role}`
- `DELETE /api/opportunities/{id}/shares/{user_id}`

**Timeline**
- `GET    /api/opportunities/{id}/timeline` — supports
  `?q=&type=&from=&to=&author_id=`
- `POST   /api/opportunities/{id}/timeline`
- `PATCH  /api/timeline/{entry_id}`
- `DELETE /api/timeline/{entry_id}` — soft delete

**Notes**
- `POST   /api/timeline/{entry_id}/notes`
- `PATCH  /api/notes/{note_id}` — sets `edited = true` and appends a
  NoteVersion row
- `GET    /api/notes/{note_id}/versions`
- `DELETE /api/notes/{note_id}` — soft delete

**Comments**
- `POST   /api/notes/{note_id}/comments`
- `DELETE /api/comments/{comment_id}` — soft delete, author or Owner only

**AI Agent**
- `POST /api/opportunities/{id}/ai/ask` — `{question}` ->
  `{answer, referenced_entry_ids}`

**Export**
- `GET /api/opportunities/{id}/export/pdf`
- `GET /api/opportunities/{id}/export/csv`
- `GET /api/opportunities/{id}/export/json`

**Notifications**
- `GET   /api/notifications`
- `PATCH /api/notifications/{id}/read`

**Audit Log**
- `GET /api/opportunities/{id}/audit-log` — owner only

All endpoints except `/api/auth/*` require a valid session and enforce the
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
- [ ] Invite by email, assign/change/remove role
- [ ] Audit log entries for share/role changes
- [ ] Auto-logged system timeline entries for share/role changes
- Acceptance: Owner shares with a second test user, who sees the opportunity
  with the correct permissions

**Phase 4 — AI Agent**
- [ ] Backend assembles chronological timeline text, calls OpenAI
- [ ] Sidebar chat UI, per-opportunity conversation
- Acceptance: asking "summarize this opportunity" returns a grounded answer
  referencing actual entries

**Phase 5 — Export**
- [ ] PDF export via WeasyPrint (opportunity summary + full timeline)
- [ ] CSV and JSON export of raw data
- Acceptance: exported PDF renders all entries/notes/comments in chronological
  order and matches the on-screen timeline

**Phase 6 — Notifications and Reminders**
- [ ] @mentions -> Notification rows, notification bell UI
- [ ] Stalled-opportunity flag using 14 days since latest non-deleted timeline
      activity
- [ ] Follow-up reminder field on entries
- Acceptance: mentioning a colleague creates a notification they can see and
  dismiss

**Phase 7 — Polish**
- [ ] Apply color scheme, responsive layout, empty states, loading states
- [ ] Complete the phase gates in `docs/TEST_CRITERIA.md`
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
