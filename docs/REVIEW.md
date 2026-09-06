# OppTrail — Phase 1 Review and Inventory

Reviewed at `1077f74` on branch `fix/code-review-findings` (one commit ahead of
`main`). That commit resolved findings 1-9 of `docs/code_review.md`; this document
reflects the code as it stands now, not the pre-fix state.

Scope: complete read of `backend/app` (14 modules, ~1,100 lines), `backend/tests`
(8 files, 39 tests), `frontend/app` (3 files, 2,786 lines), `Dockerfile`,
`scripts/`, and the planning documents.

---

## 1. Feature inventory

Rows follow the 19 numbered requirements in `AGENTS.md`.

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| 1 | User can sign in | Implemented | `routes_auth.py` (signup/login/logout/me), `auth.py:28-84`, bcrypt via passlib `auth.py:13` |
| 2 | Three-level timeline tree | Implemented | `schema.sql:50-101`, `routes_timeline.py:133-273` assembles entries → notes → comments in 3 batched queries |
| 3 | Notes addable to any entry at any time | Implemented | `routes_timeline.py:430` — no temporal constraint on `entry_id` |
| 4 | Comments on any note | Implemented | `routes_timeline.py:628` |
| 5 | Read-only AI sidebar | Implemented | `routes_ai.py:20-52`, `ai_service.py:124-137`; no tool surface exposed |
| 6 | Share as Viewer / Editor | Implemented | `routes_sharing.py:77-170`, `permissions.py` |
| 7 | PDF export | Implemented | `export_service.py:219-233` (WeasyPrint), verified rendering in-container |
| 8 | Dashboard grouped by stage | Implemented | `routes_opportunities.py:136`, `page.tsx` `groupedOpportunities` |
| 9 | Opportunity record fields | Implemented | `schema.sql:16-37` |
| 10 | Auto system timeline entries | Implemented | `timeline_utils.py`, called from `routes_opportunities.py` (create, stage change) and `routes_sharing.py` (share added/changed/removed) |
| 11 | Entry types with colour/icon | **Partial** | 8 types with colour markers (`globals.css` `.timeline-marker`, `.type-badge`); **no icons** |
| 12 | Search and filter | **Partial** | `routes_timeline.py:142-210` covers keyword/type/date/author, but author filter is a raw numeric ID input (`page.tsx` "Author ID"); keyword is `LIKE` over 4 columns with no index |
| 13 | @mentions notify | **Partial** | `notification_service.py:6-90` matches `@email@domain.tld`; **no autocomplete, no hint, mention not linkified** — undiscoverable without reading the source |
| 14 | Notification bell | **Partial** | `routes_notifications.py`; **unread-only** (`:33 read = 0`), so marking read destroys the record from the user's view. No history, no preferences, no batching |
| 15 | Note edit history | Implemented | `note_versions` table, `routes_timeline.py:490-592`. Strongest part of the data model |
| 16 | Stalled flag + follow-up reminder | Implemented | `routes_opportunities.py:26-70` (14-day SQL threshold), `follow_up_date` on entries |
| 17 | Sanitized Markdown rich text | **Partial** | Render path is correct (`page.tsx` `MarkdownText`, `rehype-sanitize` with `http`/`https`/`mailto` allowlist). **Composers are single-line `<input>`** so bullet lists cannot be typed; **PDF escapes Markdown to literal text** (`export_service.py:247`) |
| 18 | Full audit log incl. deletions | Implemented | `audit_utils.py`; share changes in `routes_sharing.py`, all four delete paths in `routes_timeline.py` / `routes_opportunities.py` |
| 19 | CSV / JSON export | Implemented | `routes_export.py`, `export_service.py:145-230` with formula-injection escaping |

MVP non-goals in `AGENTS.md` were all correctly respected: no attachments, no
email/calendar integration, no live co-editing, no public share links, no
organizations, no AI write access.

### Infrastructure inventory

| Concern | Status | Evidence |
|---------|--------|----------|
| Migrations | **Partial** | `database.py:34-44` re-runs `schema.sql` + additive migrations every startup. No version table, no down path, no Alembic |
| CI | **Absent** | No `.github/`, no workflow files anywhere in the repo |
| Logging | **Absent** | Zero uses of `logging` in `backend/app`. `routes_ai.py:43` catches every exception and discards the cause |
| Observability | **Absent** | No metrics, traces, health detail beyond `{"status": "ok"}` |
| Backups | **Absent** | SQLite file bind-mounted at `data/`; no snapshot, no WAL, no restore procedure |
| Pagination | **Absent** | No `LIMIT`/`OFFSET` anywhere. Every list endpoint returns the full set |
| Frontend tests | **Absent** | 1,829-line component with no test of any kind |

---

## 2. Divergences between code and planning documents

Including divergences in this brief itself, per instruction 126.

1. **This brief's stack list is wrong about the AI provider.** It states
   "OpenRouter (`gpt-oss-20b`)". The code uses the OpenAI SDK directly —
   `ai_service.py:4` `from openai import OpenAI`, `:130` `OpenAI(api_key=...)`,
   `:131` `client.responses.create`, configured by `OPENAI_API_KEY` /
   `OPENAI_MODEL` (`settings.py:7-8`, default `gpt-5.6-luna`). `AGENTS.md` also
   says "Use OpenAI for AI calls." Nothing in the repository references
   OpenRouter. **This needs correcting before it drives an ADR** — the two have
   different SDKs, auth, model catalogues, and failure modes.
2. **This brief says entries carry attachments.** They do not, and attachments are
   an explicit MVP non-goal in `AGENTS.md`. Phase 2 treats them as new work.
3. **`PLAN.md:22-24` promises timeline polling** — "the frontend polls the timeline
   endpoint on an interval while an opportunity view is open." There is no
   `setInterval` in the codebase; there is a manual Refresh button. Two colleagues
   on one opportunity currently do not see each other's writes.
4. **`PLAN.md` OpportunityShare omits `deleted_at`**, which the schema has
   (`schema.sql:46`) and which the permission join depends on
   (`permissions.py:22`).
5. **`settings.py:9` `session_secret` is dead configuration** — declared,
   documented in `README.md` and `.env.example`, referenced nowhere. Sessions are
   random opaque IDs in a table (`auth.py:29`), which need no signing key.
6. **`TEST_CRITERIA.md` claims ≥80% coverage of business logic.** Backend is 93%
   by line, which passes; but the frontend — where roughly 60% of the code lives —
   has zero coverage, so the number flatters the real state.

---

## 3. Quality assessment

### 3.1 Data model

**Sound.** Normalized to 3NF, correct FKs, `PRAGMA foreign_keys = ON` per
connection (`database.py:21`), CHECK constraints on all enumerations
(`schema.sql:23-31`, `:53-62`, `:43`), and `UNIQUE (opportunity_id, user_id)` on
shares. Soft deletes are applied consistently and cascaded manually, with every
read filtering `deleted_at IS NULL` at each tree level. `note_versions` is a
genuine append-only history.

**Timestamps are now correct and must stay that way.** All timestamps are `TEXT`
in one canonical fixed-width UTC format (`time_utils.py`), which is what makes
lexicographic comparison in SQLite equal chronological comparison. This is an
invariant, not a style choice — the previous mixed format silently reordered
timelines and dropped rows from date filters. Any v2 schema work must preserve it,
and Postgres migration (ADR 1) is the natural point to move to real `timestamptz`.

**Indexing is thin — the clearest data-layer gap.** Nine indexes exist
(`schema.sql:121-129`), all single-column FK lookups. Missing for known access
patterns:
- `timeline_entries(opportunity_id, event_timestamp)` — every timeline read
  filters on the first and orders by the second (`routes_timeline.py:220`).
- No index includes `deleted_at`, though every read filters it. Partial indexes
  (`WHERE deleted_at IS NULL`) are the right shape.
- Keyword search is four `LIKE '%…%'` predicates plus two correlated `EXISTS`
  subqueries (`routes_timeline.py:148-173`). Unindexable by construction; this is
  the FTS ADR (7).

**N+1 in two hot paths — but measure before "fixing" the first one.**
- `routes_opportunities.py:165` runs the three-way-UNION stalled query once per
  opportunity. At the confirmed scale (400 opportunities) that is 401 queries per
  dashboard load.
- `ai_service.py:59-101` runs one query per entry and one per note while building
  AI context. A 200-entry opportunity issues several hundred queries before the
  model call. This one is a straightforward batched rewrite, as `list_timeline`
  already demonstrates.

**Correction to my earlier assessment.** I claimed the dashboard N+1 was
"correctable with a single grouped query". Benchmarked against a seeded database at
the confirmed scale (800,400 rows), that is wrong — the naive grouped rewrite is
**three times slower**:

| Accessible opportunities | N+1 (current) | Single grouped query |
|---|---|---|
| 20 | 9 ms | 328 ms |
| 100 | 32 ms | 342 ms |
| 400 | 131 ms | 363 ms |

The per-opportunity query uses the `opportunity_id` index and touches only that
opportunity's rows; the grouped version builds a UNION across all 800,000 rows
before joining. The N+1 is ugly but it is **within the 300 ms budget even in the
worst case**, and the obvious fix would regress it.

The correct fix, if one is wanted, is a denormalized `last_activity_at` column on
`opportunities` maintained on write, making the dashboard O(number of
opportunities) with no subquery at all. That is a v2 schema change, not a query
rewrite — and it is optional, not urgent.

**`routes_opportunities.py:222-229` opens two sequential connections** for one
logical read of one opportunity.

### 3.2 API design

**Authorization is the strongest part of the codebase and I found no object-level
gap.** Every route resolves the role from the database via `permissions.py` rather
than trusting the client; no endpoint takes a role or owner ID from the request
body. The four helpers form a clean ladder — `require_opportunity_access`,
`require_timeline_write`, `require_delete_permission`, `require_opportunity_owner`
— and nested objects are resolved through `fetch_*_context` helpers that join up
to the opportunity before any check (`routes_timeline.py:72-126`), which is
precisely the pattern that prevents IDOR. Absence of access returns 404, not 403,
so existence does not leak (`permissions.py:47-50`). Tests cover the role matrix
per resource.

This is the one subsystem I would not restructure. The v2 risk is not that it is
wrong, but that it is enforced by convention — every new endpoint must remember to
call a helper. That is what ADR 9 needs to solve, by moving the check into a
dependency that cannot be forgotten rather than a call that can.

**Weaknesses:**
- **No pagination anywhere.** `GET /api/opportunities`, the timeline, notifications
  and the audit log all return unbounded sets. At ClickUp-scale data this is the
  first thing to break, and adding it later is a breaking API change — it belongs
  in an early v2 phase, not a late one.
- **`GET /api/notifications` returns unread only** (`routes_notifications.py:33`).
  There is no way to see a read notification, which makes the "inbox" of Phase 2
  a rewrite rather than an extension.
- **Error shapes are inconsistent by layer.** Hand-raised errors are
  `{"detail": "string"}`; Pydantic validation failures are `{"detail": [ {...} ]}`.
  The frontend guards with `typeof error.detail === "string"` (`page.tsx`
  `apiRequest`) and silently degrades every 422 to "Request failed" — so users
  never see *which* field was rejected.
- **Filter inputs are unvalidated** where they are not dangerous: `type`
  (`routes_timeline.py:175`) accepts any string rather than the `EntryType`
  literal, so a typo returns an empty list instead of a 422.
- **No API versioning.** Every route is `/api/*`. v2 will break response shapes
  (pagination envelopes, notification model); there is no way to do that
  incrementally today.

### 3.3 Frontend

**This is the weakest subsystem and the main structural obstacle to v2.**

The entire application is one 1,829-line `"use client"` component
(`page.tsx:276` `Home`) holding **28 `useState` hooks**, with exactly one other
component in the codebase (`MarkdownText`, `:256`). `frontend/app` contains three
files total.

Consequences, all of which the brief's Phase 2 feature list would make worse:

- **No server components and no data layer.** `next.config.ts` sets
  `output: "export"`, so the whole app is static-exported and every byte of data
  arrives through one hand-rolled `apiRequest` wrapper. There is no cache, no
  deduplication, no revalidation, no optimistic update, no request cancellation.
  The mutation pattern is "await the write, then refetch everything."
- **Every state change re-renders the entire application.** Typing one character in
  a comment box re-renders all opportunities, all timeline entries, all notes and
  the AI sidebar, because `commentForms` lives in the root component. Any
  keyboard-first, densely interactive v2 UI will be unusable on this foundation.
- **Refetch storms.** Writes trigger `loadTimeline` plus `loadOpportunities` (and in
  three places `loadOpportunities` twice in a row, a copy-paste defect).
- **No routing.** Views switch on `selectedOpportunityId` state, so no deep links,
  no back button, no shareable URL to an opportunity. Every Phase 2 view feature
  (saved views, board/table/calendar) assumes a URL to hang state on.
- **Accessibility is effectively absent.** One `aria-*`/`role` attribute in 1,829
  lines. No focus management, no dialogs (deletes use `window.confirm`), no
  keyboard navigation. The brief's accessibility target and command-palette
  requirement both start from zero here.
- **Loading and error states are two shared strings** (`status`, `error`) for the
  whole app, so an error from a timeline action renders in the dashboard sidebar
  far from where it happened.

**This does not need tearing out, but it does need decomposition before Phase 2
features land.** The business logic is thin and the API is clean; what is missing
is component boundaries, a router, and a data layer. Rebuilding on top of the
current single component would be more expensive than restructuring first, and
restructuring is invisible to users — which conflicts with the brief's "no phase
may be pure refactoring" rule. Resolving that tension is a roadmap question I flag
for Phase 5, and it is the single most important sequencing decision in this plan.

### 3.4 Security

**Recently fixed and verified (do not re-litigate):** unauthenticated path
traversal that exposed the whole SQLite file (`main.py:56-64` now resolves and
containment-checks), CSV formula injection (`export_service.py:14-17`), the
editor-can-delete-anything permission inversion, and unvalidated timestamps that
persisted and then 500'd the dashboard for every user on the opportunity.

**Current posture:**

- **Session handling is reasonable for the threat model.** Opaque 256-bit random
  IDs (`auth.py:29`), server-side table, HttpOnly, SameSite=Lax, 7-day expiry
  checked on every request (`auth.py:66-76`).
- **Gaps:** no `secure` flag (`auth.py:39-45`) — acceptable on
  `http://localhost`, must become environment-conditional the moment there is a
  real deployment; **expired sessions are never purged**, so the table grows
  forever; **no session rotation on login**, and no way to revoke other sessions;
  **no rate limiting on `POST /api/auth/login`**, so the only brute-force cost is
  bcrypt.
- **CSRF: adequate today, fragile as a design.** `SameSite=Lax` blocks the
  cookie on cross-site POST, and all state changes are POST/PATCH/DELETE, so there
  is no practical CSRF vector right now. But there is no second line of defence —
  no Origin check, no token — and the protection is entirely incidental. The
  moment any state-changing GET is added (an "unsubscribe" link, a share
  acceptance URL), it becomes exploitable with no test to catch it.
- **Prompt injection is a live, unmitigated surface.** `ai_service.py:134`
  interpolates timeline content directly into the model input as
  `f"Timeline context:\n{...}\n\nQuestion:\n{question}"` with no delimiting or
  escaping. Any user who can write a note on a shared opportunity — including an
  Editor invited for one deal — can inject instructions that alter what the owner's
  AI answers say. Impact is bounded today because the agent is read-only by
  construction and its output is only shown back to users who already have access,
  so the worst case is a misleading answer rather than data exfiltration or a
  write. **That bound is exactly what Phase 2's AI expansion would remove**: draft
  emails, next-best-action, and notes-to-entry parsing all convert "misleading
  text" into "action taken", and attachment/email ingestion adds content from
  people who are not even users. This is the highest-leverage security decision in
  the whole v2 plan.
- **Tenant isolation does not exist as a concept.** There is one flat user pool and
  isolation is per-opportunity, re-derived in every endpoint. The brief's
  workspace → team → opportunity hierarchy is a genuine new boundary, not an
  extension (ADR 9).
- **`passlib` 1.7.4 is unmaintained** (last release 2020) and already broken at the
  edges — every test run prints `(trapped) error reading bcrypt version` because it
  probes a `bcrypt.__about__` attribute that no longer exists. `pyproject.toml`
  pins `bcrypt<5` to hold it together. Low urgency, but it is a dependency on an
  abandoned package in the authentication path.
- **`frontend/package.json` floats eight dependencies at `"latest"`**, including
  `next`, `react`, and `typescript`. `package-lock.json` keeps `npm ci`
  reproducible today, but any lock refresh can jump majors with no diff signal.

### 3.5 Operations

**The second deploy is the problem.** `initialize_database()` (`database.py:34-44`)
runs `executescript(schema.sql)` then additive migrations on **every** startup,
guarded by `column_exists()` with no version table and no down path. It works, and
it is honest about being an MVP mechanism, but it cannot express a column rename, a
type change, a data backfill that must run exactly once, or a rollback. It also
means startup cost grows with the database:
`backfill_opportunity_created_entries` and `normalize_legacy_timestamps` scan every
row of ten columns on each boot.

- **No CI.** Nothing runs the 39 tests except a human. The failing test I found in
  the last review sat red on `main` because nothing was watching.
- **No logging.** `routes_ai.py:43` swallows every OpenAI exception into a bare 502
  with the cause discarded, which directly contradicts `AGENTS.md` standard 4
  ("prove with evidence"). There is currently no evidence to collect from a
  production incident.
- **No backups.** The SQLite file is bind-mounted from `data/`. No WAL mode
  (`database.py` sets only `foreign_keys`), so a crash mid-write is a worse
  outcome than it needs to be, and there is no snapshot or restore procedure.
- **Config is thin but sane** — `pydantic-settings` with an `.env` file. One trap:
  `env_file="../.env"` is relative to the process CWD, so the backend must be
  started from `backend/`.
- **Single-container packaging is good** and should survive as long as SQLite does
  (ADR 10). Note the build has no healthcheck, no restart policy, and runs as root.

---

## 4. Ranked findings

Findings 1-9 of `docs/code_review.md` are excluded — they are fixed at this commit.

### Blockers for a ClickUp-class product

| ID | Finding | Why it blocks |
|----|---------|---------------|
| B1 | **Frontend is one 1,829-line component with 28 `useState` hooks, no router, no data layer** (`page.tsx`) | Every Phase 2 feature — multiple views, saved views, command palette, optimistic updates, real-time — assumes component boundaries, URL state, and a cache. Building them on this multiplies the cost of each one and guarantees a later rewrite |
| B2 | **No migration tooling** (`database.py:34-44`) | Custom fields, attachments, workspaces and the notification rework all require real schema evolution. `column_exists()` guards cannot express renames, backfills or rollbacks. The brief already calls this non-negotiable and I agree |
| B3 | **No pagination on any endpoint** | A breaking API change that gets more expensive with every client feature built against the current shapes. Must land before the view layer is built, not after |
| B4 | **No CI** | 39 tests that nothing runs. Any multi-phase plan depends on a green signal that currently requires a human to remember |

### High

| ID | Finding | Evidence |
|----|---------|----------|
| H1 | Prompt injection unmitigated, and Phase 2 removes the containment that makes it survivable today | `ai_service.py:134` |
| H2 | Notifications are unread-only, so there is no inbox to extend | `routes_notifications.py:33` |
| H3 | No logging or observability anywhere in the backend | `routes_ai.py:43` |
| H4 | Authorization is correct but enforced by convention — a forgotten helper call is an unguarded endpoint | `permissions.py`, every route |
| H5 | No backups, no WAL, no restore procedure for the only copy of the data | `database.py:17-22` |
| H6 | Session hygiene: no expiry purge, no rotation on login, no revocation, no login rate limit | `auth.py:28-84` |

### Medium

| ID | Finding | Evidence |
|----|---------|----------|
| M1 | Missing composite and partial indexes for the known access patterns | `schema.sql:121-129` |
| M2 | N+1 in AI context assembly (one query per entry and per note) | `ai_service.py:59-101` |
| M3 | Keyword search is unindexable `LIKE '%…%'`; measured worst case 294 ms against a 300 ms budget, and no ranking or snippets | `routes_timeline.py:148-173` |
| M4 | Validation errors (422) are flattened to "Request failed" in the UI | `page.tsx` `apiRequest` |
| M5 | Accessibility effectively absent — one `aria`/`role` attribute in 1,829 lines | `page.tsx` |
| M6 | Requirement 17 half-delivered: single-line composers, Markdown not rendered in PDF | `page.tsx`, `export_service.py:247` |
| M7 | @mentions undiscoverable — full email required, no autocomplete, not linkified | `notification_service.py:6` |
| M8 | No API versioning ahead of known breaking changes | all routes |
| M9 | Planned timeline polling never implemented; collaborators do not see each other's writes | `PLAN.md:22-24` |

### Low

Dashboard N+1 (measured within budget — see 3.1; do not "fix" it with a grouped
query); `session_secret` dead config (`settings.py:9`); `passlib` unmaintained; eight
frontend deps floating at `"latest"`; duplicated `loadOpportunities()` calls in
three handlers; dead `{"opportunity": None}` branch (`export_service.py:39`);
`type` filter unvalidated; double connection in `get_opportunity`; author filter
requires a numeric user ID; no container healthcheck; container runs as root.

---

## 5. What needs tearing out

Only one thing, and it is not the backend.

**The frontend's single-component structure must be decomposed before Phase 2
features are built** — not rewritten from scratch, but broken into routed views,
scoped state, and a real data layer. The business logic inside it is thin and the
API it consumes is clean, so this is restructuring rather than redesign. The cost
of leaving it is that every one of the twelve Phase 2 feature areas pays a tax:
each new view adds hooks to a component that already re-renders everything, and
the interaction quality the brief is actually asking for (keyboard-first, dense,
optimistic, real-time) is unreachable without it.

**The backend should not be torn out.** The schema is sound, authorization is
correct and well-tested, soft deletes and audit trails are consistent, and the
module boundaries are sensible. It needs additions — migrations, pagination,
logging, indexes, a dependency-enforced authz boundary — not replacement. Every
one of those is additive.

I flag one tension for Phase 5 rather than resolving it here: the brief requires
that no phase be pure refactoring, but B1 and B2 are exactly that. My
recommendation is to fold the frontend decomposition into the first view-adding
phase (Board or Table view forces routing and scoped state to exist) and to fold
Alembic adoption into the first phase with a real schema change (custom fields).
Both then ship with visible outcomes. I will make that concrete in `ROADMAP.md`.

---

## 6. What I need before Phases 2-5

Clarifying questions are in this session's chat rather than a file, per the brief's
instruction to batch them and wait. `docs/OPEN-QUESTIONS.md` will capture whatever
remains unresolved after those answers.
